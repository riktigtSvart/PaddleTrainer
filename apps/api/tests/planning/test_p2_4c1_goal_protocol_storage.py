"""Real source-table and immutable audit adapters on synthetic, isolated SQLite.

These tests prove registration/replay contracts, not live PostgreSQL integration
or physiological validity. No application database or athlete dataset is read.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import app.planning.application.register_goal_protocol as service
import app.planning.infrastructure.adapters.current_training_period_goals as source_adapter
import pytest
from app.db.base import Base
from app.models.entities import (
    ObjectiveType,
    PeriodType,
    TrainingPeriod,
    TrainingPeriodObjective,
)
from app.planning.domain.common.serialization import (
    canonical_json,
    compute_content_hash,
)
from app.planning.domain.goals.protocol import GOAL_HASH_EXCLUDE, GoalVersionReference
from app.planning.domain.persistence.audit import AuditArtifactKind
from app.planning.infrastructure.adapters.current_training_period_goals import (
    SqlAlchemyTrainingGoalSource,
)
from app.planning.infrastructure.persistence.sqlalchemy_models import (
    PlanningAuditArtifactRow,
)
from app.planning.infrastructure.repositories.postgres_planning_audit import (
    SqlAlchemyPlanningAuditRepository,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from tests.planning.test_p2_4a2_planning_utility_storage import (
    AsyncSQLiteBridge,
)
from tests.planning.test_p2_4a2_planning_utility_storage import (
    database as database,  # noqa: PLC0414 -- make the shared isolated fixture visible
)
from tests.planning.test_p2_4b1_planning_utility_decision_binding import (
    precise_database as precise_database,  # noqa: PLC0414 -- microsecond DB clock
)
from tests.planning.test_p2_4c1_goal_protocol import (
    ATHLETE,
    MACRO,
    MESO,
    MESO2,
    SEASON,
    macro_proposal,
    meso_proposal,
    sources,
)

MACRO_KIND = AuditArtifactKind.MACROCYCLE_CAPABILITY_PLAN
MESO_KIND = AuditArtifactKind.MESOCYCLE_GOAL_PROTOCOL


@pytest.fixture
def goal_database(precise_database):
    Base.metadata.create_all(
        precise_database,
        tables=[
            TrainingPeriod.__table__,
            TrainingPeriodObjective.__table__,
        ],
    )
    with Session(precise_database) as sync:
        for node in sources().hierarchy + sources().mesocycles:
            row = TrainingPeriod(
                id=UUID(node.period_id),
                user_id=UUID(node.athlete_id),
                parent_id=UUID(node.parent_id) if node.parent_id else None,
                period_type=PeriodType(node.period_type.value),
                title=node.title,
                start_date=datetime.fromisoformat(node.start_date).date(),
                end_date=datetime.fromisoformat(node.end_date).date(),
                extra_data={},
            )
            sync.add(row)
            sync.flush()
            for objective in node.legacy_objectives:
                sync.add(
                    TrainingPeriodObjective(
                        period_id=row.id,
                        objective_type=ObjectiveType(objective.objective_type),
                        weight=float(objective.weight),
                    )
                )
        sync.commit()
    return precise_database


def repositories(sync):
    bridge = AsyncSQLiteBridge(sync)
    return SimpleNamespace(
        session=bridge,
        audit=SqlAlchemyPlanningAuditRepository(bridge),
        source=SqlAlchemyTrainingGoalSource(bridge),
    )


async def register_macro(repo, proposal=None):
    return await service.register_macrocycle_capability_plan(
        athlete_id=ATHLETE,
        proposal=proposal or macro_proposal(),
        source_repository=repo.source,
        audit_repository=repo.audit,
        session=repo.session,
    )


async def register_meso(repo, macro, proposal=None):
    return await service.register_mesocycle_goal_protocol(
        athlete_id=ATHLETE,
        proposal=proposal or meso_proposal(macro.artifact),
        source_repository=repo.source,
        audit_repository=repo.audit,
        session=repo.session,
    )


async def load(repo, result):
    return await service.load_cycle_goal_artifact(
        athlete_id=ATHLETE,
        artifact_kind=MACRO_KIND
        if result.artifact.schema_version.startswith("macrocycle")
        else MESO_KIND,
        artifact_id=result.artifact.artifact_id,
        available_by=datetime.now(UTC),
        audit_repository=repo.audit,
        session=repo.session,
    )


def audit_rows(engine):
    with Session(engine) as sync:
        return list(sync.scalars(select(PlanningAuditArtifactRow)))


@pytest.mark.asyncio
async def test_real_source_capture_is_one_statement_and_preserves_legacy_weights(goal_database):
    with Session(goal_database) as sync:
        repo = repositories(sync)
        snapshot = await repo.source.capture(athlete_id=ATHLETE, macrocycle_period_id=MACRO)
        assert snapshot == sources()
        assert repo.session.execute_count == 1
        assert repo.session.commit_count == 0
        await repo.session.rollback()


@pytest.mark.asyncio
async def test_source_capture_refreshes_retained_orm_identity_map(goal_database):
    with Session(goal_database, expire_on_commit=False) as sync:
        cached = sync.get(TrainingPeriod, UUID(MACRO))
        sync.commit()
        with Session(goal_database) as writer:
            writer.execute(
                update(TrainingPeriod)
                .where(TrainingPeriod.id == UUID(MACRO))
                .values(title="fresh database title")
            )
            writer.commit()
        assert cached.title != "fresh database title"
        repo = repositories(sync)
        snapshot = await repo.source.capture(athlete_id=ATHLETE, macrocycle_period_id=MACRO)
        assert snapshot.hierarchy[-1].title == "fresh database title"
        await repo.session.rollback()


@pytest.mark.asyncio
async def test_macro_and_protocol_commit_and_reload_from_an_independent_session(goal_database):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        macro = await register_macro(repo)
        protocol = await register_meso(repo, macro)
        assert repo.session.commit_count == 2
        assert repo.session.in_transaction() is False
        assert macro.measurement_schedule_preregistered is False
        assert protocol.measurement_schedule_preregistered is True
        assert protocol.comparative_utility_endpoint_preregistered is False
        assert protocol.planning_authorized is False
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        restored = await load(repo, protocol)
        assert restored.artifact == protocol.artifact
        assert restored.durable_available_at == protocol.durable_available_at
        assert repo.session.commit_count == 0
        assert repo.session.in_transaction() is False
    assert len(audit_rows(goal_database)) == 2


@pytest.mark.asyncio
async def test_retry_and_load_freeze_original_periods_after_mutable_changes(
    goal_database, monkeypatch
):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        macro = await register_macro(repo)
        protocol = await register_meso(repo, macro)
        with Session(goal_database) as writer:
            writer.execute(
                update(TrainingPeriod)
                .where(TrainingPeriod.id == UUID(MACRO))
                .values(title="edited after registration")
            )
            writer.execute(
                update(TrainingPeriodObjective)
                .where(
                    TrainingPeriodObjective.period_id == UUID(MESO),
                    TrainingPeriodObjective.objective_type == ObjectiveType.ENDURANCE,
                )
                .values(weight=0.5)
            )
            writer.commit()

        async def no_recapture(**kwargs):
            raise AssertionError("Immutable retry attempted mutable source recapture")

        monkeypatch.setattr(repo.source, "capture", no_recapture)
        retried_macro = await register_macro(repo)
        retried_meso = await register_meso(repo, macro)
        assert retried_macro.reused_registration and retried_meso.reused_registration
        assert retried_macro.artifact == macro.artifact
        assert retried_meso.artifact == protocol.artifact
        assert repo.session.commit_count == 2
        assert (await load(repo, protocol)).artifact == protocol.artifact


@pytest.mark.asyncio
async def test_new_protocol_rejects_changed_period_sources(goal_database):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        macro = await register_macro(repo)
        with Session(goal_database) as writer:
            writer.execute(
                update(TrainingPeriod)
                .where(TrainingPeriod.id == UUID(MESO))
                .values(title="changed phase")
            )
            writer.commit()
        with pytest.raises(ValueError, match="changed"):
            await register_meso(repo, macro)
        assert len(audit_rows(goal_database)) == 1
        assert repo.session.in_transaction() is False


@pytest.mark.asyncio
async def test_explicit_new_macro_and_protocol_revisions_preserve_old_versions(goal_database):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        first = await register_macro(repo)
        original = await register_meso(repo, first)
        proposal = replace(
            macro_proposal(),
            revision=2,
            supersedes=GoalVersionReference(
                first.artifact.artifact_id, first.artifact.content_hash
            ),
            rationale="reviewed revision",
        )
        second = await register_macro(repo, proposal)
        next_protocol = replace(
            meso_proposal(second.artifact),
            revision=2,
            supersedes=GoalVersionReference(
                original.artifact.artifact_id, original.artifact.content_hash
            ),
        )
        changed = await register_meso(repo, second, next_protocol)
        assert changed.artifact.macrocycle_source.artifact_id == second.artifact.artifact_id
        assert (await load(repo, original)).artifact == original.artifact
        assert (await load(repo, first)).artifact == first.artifact
        assert len(audit_rows(goal_database)) == 4


@pytest.mark.asyncio
async def test_reusing_one_version_for_changed_intent_conflicts(goal_database):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        await register_macro(repo)
        with pytest.raises(service.CycleGoalProtocolError, match="different intent"):
            await register_macro(repo, replace(macro_proposal(), rationale="changed"))
        assert len(audit_rows(goal_database)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["existing_transaction", "other_source_session", "other_audit_session"]
)
async def test_transaction_ownership_is_checked_before_reads(goal_database, mode):
    with Session(goal_database) as sync:
        repo = repositories(sync)
        if mode == "existing_transaction":
            sync.execute(select(1))
        elif mode == "other_source_session":
            repo.source.session = object()
        else:
            repo.audit.session = object()
        with pytest.raises(service.CycleGoalProtocolError):
            await register_macro(repo)
        assert repo.session.execute_count == 0
        assert repo.session.rollback_count == 0
        if mode == "existing_transaction":
            assert sync.in_transaction()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["fail_commit", "skip_commit"])
async def test_failed_or_skipped_commit_never_returns_a_durable_receipt(goal_database, mode):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        setattr(repo.session, mode, True)
        with pytest.raises(RuntimeError):
            await register_macro(repo)
        assert repo.session.rollback_count == 1
        assert repo.session.in_transaction() is False
        assert audit_rows(goal_database) == []


@pytest.mark.asyncio
async def test_uncertain_commit_is_recovered_by_exact_retry(goal_database, monkeypatch):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        original_commit = repo.session.commit

        async def commit_then_raise():
            await original_commit()
            raise RuntimeError("connection lost after synthetic commit")

        monkeypatch.setattr(repo.session, "commit", commit_then_raise)
        with pytest.raises(RuntimeError):
            await register_macro(repo)
        assert len(audit_rows(goal_database)) == 1
        recovered = await register_macro(repo)
        assert recovered.reused_registration
        assert recovered.registration_committed
        assert len(audit_rows(goal_database)) == 1


@pytest.mark.asyncio
async def test_source_limit_is_completeness_unknown_not_partial_registration(
    goal_database, monkeypatch
):
    monkeypatch.setattr(source_adapter, "TRAINING_GOAL_SOURCE_ROW_LIMIT", 4)
    with Session(goal_database) as sync:
        repo = repositories(sync)
        with pytest.raises(ValueError, match="completeness"):
            await register_macro(repo)
        assert audit_rows(goal_database) == []
        assert repo.session.in_transaction() is False


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["missing_ancestor", "cycle", "overlap", "wrong_period_type"])
async def test_real_adapter_rejects_ambiguous_or_incomplete_hierarchy(goal_database, mode):
    with Session(goal_database) as writer:
        if mode == "missing_ancestor":
            writer.execute(
                update(TrainingPeriod)
                .where(TrainingPeriod.id == UUID(MACRO))
                .values(parent_id=UUID("99999999-9999-4999-8999-999999999999"))
            )
        elif mode == "cycle":
            writer.execute(
                update(TrainingPeriod)
                .where(TrainingPeriod.id == UUID(SEASON))
                .values(parent_id=UUID(MACRO))
            )
        elif mode == "overlap":
            writer.execute(
                update(TrainingPeriod)
                .where(TrainingPeriod.id == UUID(MESO2))
                .values(start_date=datetime(2030, 1, 30).date())
            )
        else:
            writer.execute(
                update(TrainingPeriod)
                .where(TrainingPeriod.id == UUID(MESO))
                .values(period_type=PeriodType.SEASON)
            )
        writer.commit()
    with Session(goal_database) as sync:
        repo = repositories(sync)
        with pytest.raises(ValueError):
            await register_macro(repo)
        assert audit_rows(goal_database) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    [
        "artifact_id",
        "athlete_id",
        "schema_version",
        "content_hash",
        "content_hash_algorithm",
        "created_at",
        "persisted_at",
    ],
)
async def test_load_rejects_tampered_record_metadata(goal_database, monkeypatch, field):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        result = await register_macro(repo)
        original_get = repo.audit.get

        async def changed(**kwargs):
            record = await original_get(**kwargs)
            if field == "created_at":
                value = record.created_at - timedelta(seconds=1)
            elif field == "persisted_at":
                value = None
            else:
                value = "tampered"
            return replace(record, **{field: value})

        monkeypatch.setattr(repo.audit, "get", changed)
        with pytest.raises((ValueError, service.CycleGoalProtocolError)):
            await load(repo, result)
        assert repo.session.in_transaction() is False


@pytest.mark.asyncio
async def test_rehashed_unsupported_authority_is_rejected_by_replay(goal_database):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        result = await register_macro(repo)
        forged = replace(
            result.artifact, authority=replace(result.artifact.authority, planning_authorized=True)
        )
        forged = replace(
            forged, content_hash=compute_content_hash(forged, exclude_fields=GOAL_HASH_EXCLUDE)
        )
        with Session(goal_database) as writer:
            writer.execute(
                update(PlanningAuditArtifactRow)
                .where(PlanningAuditArtifactRow.artifact_id == result.artifact.artifact_id)
                .values(contract_json=canonical_json(forged), content_hash=forged.content_hash)
            )
            writer.commit()
        with pytest.raises(service.CycleGoalProtocolError, match="replay"):
            await load(repo, result)


@pytest.mark.asyncio
async def test_parent_full_contract_digest_protects_hash_excluded_creation_time(goal_database):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        macro = await register_macro(repo)
        protocol = await register_meso(repo, macro)
        changed = replace(
            macro.artifact, created_at=macro.artifact.created_at - timedelta(seconds=1)
        )
        assert changed.content_hash == macro.artifact.content_hash
        with Session(goal_database) as writer:
            writer.execute(
                update(PlanningAuditArtifactRow)
                .where(PlanningAuditArtifactRow.artifact_id == macro.artifact.artifact_id)
                .values(contract_json=canonical_json(changed), created_at=changed.created_at)
            )
            writer.commit()
        with pytest.raises(service.CycleGoalProtocolError, match="macrocycle goal source changed"):
            await load(repo, protocol)


@pytest.mark.asyncio
async def test_parent_missing_does_not_fall_back_to_mutable_periods(goal_database, monkeypatch):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        macro = await register_macro(repo)
        protocol = await register_meso(repo, macro)
        original = repo.audit.get

        async def missing(**kwargs):
            return None if kwargs["artifact_kind"] == MACRO_KIND else await original(**kwargs)

        monkeypatch.setattr(repo.audit, "get", missing)
        with pytest.raises(service.CycleGoalArtifactNotFound):
            await load(repo, protocol)


@pytest.mark.asyncio
async def test_save_readback_and_database_baseline_boundary_are_fail_closed(
    goal_database, monkeypatch
):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        macro = await register_macro(repo)
        proposal = meso_proposal(macro.artifact)
        original_get, original_save = repo.audit.get, repo.audit.save
        saved = False

        async def save(record):
            nonlocal saved
            value = await original_save(record)
            saved = True
            monkeypatch.setattr(
                service,
                "_utc_now",
                lambda: proposal.endpoints[0].baseline_window.starts_at + timedelta(seconds=1),
            )
            return value

        async def get(**kwargs):
            record = await original_get(**kwargs)
            if saved and record is not None and kwargs["artifact_kind"] == MESO_KIND:
                return replace(record, persisted_at=proposal.endpoints[0].baseline_window.starts_at)
            return record

        monkeypatch.setattr(repo.audit, "save", save)
        monkeypatch.setattr(repo.audit, "get", get)
        with pytest.raises(service.CycleGoalProtocolError, match="before every baseline"):
            await register_meso(repo, macro, proposal)
        assert len(audit_rows(goal_database)) == 1


@pytest.mark.asyncio
async def test_goal_context_reference_is_optional_durable_and_cutoff_checked(goal_database):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        macro = await register_macro(repo)
        protocol = await register_meso(repo, macro)
        reference = await service.load_mesocycle_goal_context_source(
            athlete_id=ATHLETE,
            artifact_id=protocol.artifact.artifact_id,
            available_by=datetime.now(UTC),
            audit_repository=repo.audit,
            session=repo.session,
        )
        assert reference.object_id == protocol.artifact.artifact_id
        assert reference.available_at == protocol.durable_available_at
        assert reference.domain == "MESOCYCLE_GOAL_PROTOCOL"
        with pytest.raises(service.CycleGoalProtocolError):
            await service.load_cycle_goal_artifact(
                athlete_id=ATHLETE,
                artifact_kind=MESO_KIND,
                artifact_id=protocol.artifact.artifact_id,
                available_by=protocol.durable_available_at - timedelta(microseconds=1),
                audit_repository=repo.audit,
                session=repo.session,
            )


@pytest.mark.asyncio
async def test_wrong_athlete_cannot_restore_another_athletes_protocol(goal_database):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        result = await register_macro(repo)
        with pytest.raises(service.CycleGoalProtocolError):
            await service.load_cycle_goal_artifact(
                athlete_id=SEASON,
                artifact_kind=MACRO_KIND,
                artifact_id=result.artifact.artifact_id,
                available_by=datetime.now(UTC),
                audit_repository=repo.audit,
                session=repo.session,
            )


@pytest.mark.asyncio
async def test_skipped_read_rollback_never_returns_a_successful_receipt(goal_database, monkeypatch):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        result = await register_macro(repo)

        async def skip_rollback():
            return None

        monkeypatch.setattr(repo.session, "rollback", skip_rollback)
        with pytest.raises(service.CycleGoalProtocolError, match="did not close"):
            await load(repo, result)


@pytest.mark.asyncio
async def test_changed_measurement_procedure_requires_a_new_procedure_version(goal_database):
    with Session(goal_database, expire_on_commit=False) as sync:
        repo = repositories(sync)
        macro = await register_macro(repo)
        first = await register_meso(repo, macro)
        proposal = replace(
            first.artifact.proposal,
            revision=2,
            supersedes=GoalVersionReference(
                first.artifact.artifact_id, first.artifact.content_hash
            ),
        )
        altered = replace(
            proposal.endpoints[0],
            procedure=replace(
                proposal.endpoints[0].procedure, procedure="different test procedure"
            ),
        )
        proposal = replace(proposal, endpoints=(altered,) + proposal.endpoints[1:])
        with pytest.raises(service.CycleGoalProtocolError, match="new procedure version"):
            await register_meso(repo, macro, proposal)
        altered = replace(altered, procedure=replace(altered.procedure, protocol_version="2"))
        accepted = await register_meso(
            repo, macro, replace(proposal, endpoints=(altered,) + proposal.endpoints[1:])
        )
        assert accepted.artifact.proposal.revision == 2
