"""Actual-decision bindings on an isolated file SQLite database.

Reuse the P2.4A synthetic source/context and the production SQLAlchemy audit
adapter. SQLite's default clock truncates seconds, so this fixture supplies
a microsecond current_timestamp database function to exercise the strict
PostgreSQL chronology contract without sleeps. No real athlete data is used.
"""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

import app.planning.application.bind_planning_utility_decision as binding_service
import app.planning.application.make_observed_planner_run as observation_service
from app.db.base import Base
from app.planning.domain.common.serialization import canonical_json, compute_content_hash
from app.planning.domain.context.models import CONTEXT_HASH_EXCLUDE_FIELDS
from app.planning.domain.decision.models import (
    PLANNER_DECISION_HASH_EXCLUDE_FIELDS,
    PlannerDecision,
    PlannerDecisionStatus,
)
from app.planning.domain.persistence.audit import (
    AuditArtifactConflictError,
    AuditArtifactKind,
)
from app.planning.domain.planning_utility.decision_binding import (
    DECISION_BINDING_HASH_EXCLUDE_FIELDS,
    PlanningUtilityDecisionArtifactReference,
    PlanningUtilityDecisionBinding,
    build_planning_utility_decision_binding,
    restore_utility_contract,
)
from app.planning.domain.rationale.models import RATIONALE_HASH_EXCLUDE_FIELDS
from app.planning.domain.replay.models import RUN_RECORD_HASH_EXCLUDE_FIELDS
from app.planning.domain.training_dynamics.prospective_validation_evidence import (
    PROSPECTIVE_VALIDATION_EVIDENCE_HASH_EXCLUDE_FIELDS,
)
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from tests.planning.test_p2_4a2_planning_utility_storage import (
    ATHLETE,
    AsyncSQLiteBridge,
    _evidence,
    _kwargs,
    _rows,
    _seed_evidence,
)
from tests.planning.test_p2_4a2_planning_utility_storage import (
    database as database,  # noqa: PLC0414 -- re-export the existing pytest fixture
)

BINDING_KIND = AuditArtifactKind.PLANNING_UTILITY_DECISION_BINDING
RUN_KINDS = (
    AuditArtifactKind.PLANNER_INPUT_ENVELOPE,
    AuditArtifactKind.CANDIDATE_ACTION_SET,
    AuditArtifactKind.PLANNING_POLICY_SET,
    AuditArtifactKind.PLANNER_DECISION,
    AuditArtifactKind.DECISION_RATIONALE,
    AuditArtifactKind.PLANNER_RUN_RECORD,
)


@pytest.fixture
def precise_database(database):
    def install_clock(connection, _record):
        connection.create_function(
            "current_timestamp",
            0,
            lambda: datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f"),
        )

    event.listen(database, "connect", install_clock)
    with database.connect() as connection:
        install_clock(connection.connection.driver_connection, None)
    yield database
    event.remove(database, "connect", install_clock)


@pytest_asyncio.fixture
async def receipt(precise_database, monkeypatch):
    source = await _seed_evidence(precise_database, monkeypatch)
    with Session(precise_database, expire_on_commit=False) as sync:
        bridge = AsyncSQLiteBridge(sync)
        kwargs = _kwargs(source, bridge)
        observed = await observation_service.make_observed_planner_run(**kwargs)
        yield SimpleNamespace(
            engine=precise_database,
            source=source,
            bridge=bridge,
            kwargs=kwargs,
            observed=observed,
            repository=kwargs["audit_repository"],
        )


def _persist_kwargs(receipt):
    return {
        "context": receipt.kwargs["context"],
        "request": receipt.kwargs["request"],
        "observed_run": receipt.observed,
        "audit_repository": receipt.repository,
        "session": receipt.bridge,
    }


def _load_kwargs(receipt):
    result = _persist_kwargs(receipt)
    result.pop("observed_run")
    return result


def _pure_kwargs(receipt):
    run = receipt.observed.planner_run
    persisted = run.decision.created_at + timedelta(microseconds=100)
    refs = tuple(
        PlanningUtilityDecisionArtifactReference(
            record.artifact_kind,
            record.artifact_id,
            record.schema_version,
            record.content_hash,
            persisted,
        )
        for record in binding_service._run_records(ATHLETE, run)
    )
    return {
        "observation": receipt.observed.registration.observation,
        "observation_persisted_at": receipt.observed.registration.durable_registered_at,
        "decision": run.decision,
        "rationale": run.rationale,
        "run_record": run.run_record,
        "artifact_refs": refs,
        "created_at": persisted + timedelta(microseconds=100),
    }


def _rehash(artifact, excluded):
    return replace(artifact, content_hash=compute_content_hash(artifact, exclude_fields=excluded))


def _assert_only_registration(receipt):
    assert len(_rows(receipt.engine, AuditArtifactKind.PLANNING_UTILITY_OBSERVATION)) == 1
    assert _rows(receipt.engine, BINDING_KIND) == ()
    for kind in RUN_KINDS:
        assert _rows(receipt.engine, kind) == ()
    assert receipt.bridge.in_transaction() is False


async def _completed(receipt):
    return await binding_service.persist_observed_planner_run_decision(**_persist_kwargs(receipt))


@pytest.mark.asyncio
async def test_workflow_commits_registration_before_actual_run_and_commits_all_artifacts(
    precise_database,
    monkeypatch,
):
    source = await _seed_evidence(precise_database, monkeypatch)
    original_make = observation_service.planner.make_auditable_planner_run
    calls = []
    with Session(precise_database, expire_on_commit=False) as sync:
        bridge = AsyncSQLiteBridge(sync)
        kwargs = _kwargs(source, bridge)

        def checked_make(**arguments):
            calls.append(arguments)
            assert bridge.commit_count == 1
            assert bridge.in_transaction() is False
            assert len(_rows(precise_database, AuditArtifactKind.PLANNING_UTILITY_OBSERVATION)) == 1
            assert _rows(precise_database, BINDING_KIND) == ()
            return original_make(**arguments)

        original_save = kwargs["audit_repository"].save

        async def checked_save(record):
            if record.artifact_kind == BINDING_KIND:
                for kind in (*RUN_KINDS, BINDING_KIND):
                    assert _rows(precise_database, kind) == ()
            return await original_save(record)

        monkeypatch.setattr(observation_service.planner, "make_auditable_planner_run", checked_make)
        monkeypatch.setattr(kwargs["audit_repository"], "save", checked_save)
        result = await binding_service.make_durable_observed_planner_run(**kwargs)
        assert len(calls) == 1
        assert result.planner_run == original_make(**calls[0])
        assert bridge.commit_count == 2
        assert bridge.in_transaction() is False
        assert result.binding_committed is True
        assert result.reused_durable_binding is False
        assert result.predecision_registration_established is True
        assert result.binding.predecision_registration_established is True
        assert result.observation.predecision_registration_established is False
        assert result.binding.observation_persisted_at < result.binding.decision_time
        assert result.binding.decision_time <= result.binding.created_at <= result.durable_bound_at
        for name in (
            "execution_binding_established",
            "response_binding_established",
            "utility_endpoint_preregistered",
            "utility_assessment_established",
            "planning_utility_supported",
            "causal_attribution_established",
            "prescription_change_authorized",
            "planning_authorized",
            "planner_runtime_modified",
            "candidate_authority_modified",
        ):
            assert getattr(result.binding, name) is False
        for kind in (*RUN_KINDS, BINDING_KIND):
            assert len(_rows(precise_database, kind)) == 1
        assert _rows(precise_database, BINDING_KIND)[0].contract_json == canonical_json(
            result.binding
        )


@pytest.mark.asyncio
async def test_retained_receipt_retry_and_read_only_restore_preserve_original_binding(
    receipt, monkeypatch
):
    first = await _completed(receipt)

    def no_new_decision(**kwargs):
        pytest.fail("Receipt persistence and load must not issue another planner run.")

    monkeypatch.setattr(observation_service.planner, "make_auditable_planner_run", no_new_decision)
    monkeypatch.setattr(binding_service, "make_observed_planner_run", no_new_decision)
    second = await _completed(receipt)
    assert second.reused_durable_binding is True
    assert second.binding == first.binding
    assert second.durable_bound_at == first.durable_bound_at
    commits = receipt.bridge.commit_count
    rollbacks = receipt.bridge.rollback_count
    original_rows = {kind: _rows(receipt.engine, kind) for kind in (*RUN_KINDS, BINDING_KIND)}

    async def no_save_or_census(*args, **kwargs):
        pytest.fail("Completed-receipt restore must only read exact frozen source references.")

    monkeypatch.setattr(receipt.repository, "save", no_save_or_census)
    monkeypatch.setattr(receipt.repository, "list_for_athlete", no_save_or_census)
    loaded = await binding_service.load_planning_utility_decision(**_load_kwargs(receipt))
    assert loaded.binding == first.binding
    assert loaded.planner_run == first.planner_run
    assert loaded.observation == first.observation
    assert loaded.durable_bound_at == first.durable_bound_at
    assert receipt.bridge.commit_count == commits
    assert receipt.bridge.rollback_count == rollbacks + 1
    assert receipt.bridge.in_transaction() is False
    assert {kind: _rows(receipt.engine, kind) for kind in original_rows} == original_rows


@pytest.mark.asyncio
async def test_later_evidence_does_not_rewrite_frozen_registration_on_restore(receipt):
    first = await _completed(receipt)
    new_source = _evidence(
        as_of=receipt.source.evidence.as_of + timedelta(seconds=1),
        created_at=receipt.source.evidence.created_at,
    )
    record = binding_service._record(
        artifact_kind=AuditArtifactKind.PROSPECTIVE_VALIDATION_EVIDENCE,
        artifact_id=new_source.evidence_id,
        athlete_id=ATHLETE,
        schema_version=new_source.schema_version,
        created_at=new_source.created_at,
        artifact=new_source,
    )
    await receipt.repository.save(record)
    await receipt.bridge.commit()
    assert len(_rows(receipt.engine, AuditArtifactKind.PROSPECTIVE_VALIDATION_EVIDENCE)) == 2
    loaded = await binding_service.load_planning_utility_decision(**_load_kwargs(receipt))
    assert loaded.binding == first.binding
    assert loaded.observation.available_validation_evidence_count == 1


@pytest.mark.asyncio
async def test_identical_policy_content_does_not_collide_between_athletes(receipt):
    first = await _completed(receipt)
    other_athlete = "22222222-2222-4222-8222-222222222222"
    users = Base.metadata.tables["users"]
    values = {"id": UUID(other_athlete)}
    if "email" in users.c:
        values["email"] = "p24b-synthetic@example.invalid"
    if "timezone" in users.c:
        values["timezone"] = "Europe/Budapest"
    if "created_at" in users.c:
        values["created_at"] = receipt.bridge.session.scalar(select(func.current_timestamp()))
    receipt.bridge.session.execute(users.insert().values(**values))
    source = _rehash(
        replace(receipt.source.evidence, athlete_id=other_athlete),
        PROSPECTIVE_VALIDATION_EVIDENCE_HASH_EXCLUDE_FIELDS,
    )
    source = replace(
        source, evidence_id="pt-prospective-validation-evidence:" + source.content_hash
    )
    await receipt.repository.save(
        binding_service._record(
            artifact_kind=AuditArtifactKind.PROSPECTIVE_VALIDATION_EVIDENCE,
            artifact_id=source.evidence_id,
            athlete_id=other_athlete,
            schema_version=source.schema_version,
            created_at=source.created_at,
            artifact=source,
        )
    )
    await receipt.bridge.commit()
    source_row = await receipt.repository.get(
        artifact_kind=AuditArtifactKind.PROSPECTIVE_VALIDATION_EVIDENCE,
        artifact_id=source.evidence_id,
    )
    await receipt.bridge.rollback()
    context = _rehash(
        replace(receipt.kwargs["context"], athlete_id=other_athlete, context_id="other-context"),
        CONTEXT_HASH_EXCLUDE_FIELDS,
    )
    request = replace(
        receipt.kwargs["request"],
        request_id="other-request",
        context_id=context.context_id,
        context_hash=context.content_hash,
        requested_at=source_row.persisted_at,
    )
    kwargs = dict(
        receipt.kwargs,
        context=context,
        request=request,
        run_id="other-run",
        decision_id="other-decision",
        rationale_id="other-rationale",
        observation_created_at=request.requested_at,
    )
    second = await binding_service.make_durable_observed_planner_run(**kwargs)
    assert first.planner_run.policy_set == second.planner_run.policy_set
    assert first.binding.artifact_refs[2].artifact_id != second.binding.artifact_refs[2].artifact_id
    assert len(_rows(receipt.engine, AuditArtifactKind.PLANNING_POLICY_SET)) == 2
    loaded = await binding_service.load_planning_utility_decision(**_load_kwargs(receipt))
    assert loaded.binding == first.binding


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ("raise", "no_commit"))
async def test_failed_binding_commit_rolls_back_all_run_artifacts_and_retains_registration(
    receipt,
    monkeypatch,
    failure,
):
    receipt.bridge.fail_commit = failure == "raise"
    receipt.bridge.skip_commit = failure == "no_commit"
    with pytest.raises(RuntimeError):
        await _completed(receipt)
    _assert_only_registration(receipt)
    assert receipt.bridge.commit_count == 1
    receipt.bridge.fail_commit = receipt.bridge.skip_commit = False

    def no_new_decision(**kwargs):
        pytest.fail("Orphan registration must not be automatically re-executed.")

    monkeypatch.setattr(observation_service.planner, "make_auditable_planner_run", no_new_decision)
    with pytest.raises(observation_service.ObservedPlannerRunError, match="explicit recovery"):
        await binding_service.make_durable_observed_planner_run(**receipt.kwargs)
    _assert_only_registration(receipt)
    with pytest.raises(binding_service.PlanningUtilityDecisionBindingNotFound):
        await binding_service.load_planning_utility_decision(**_load_kwargs(receipt))
    recovered = await _completed(receipt)
    assert recovered.binding_committed is True
    assert recovered.planner_run == receipt.observed.planner_run


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ("request", "decision", "rationale", "run"))
async def test_hash_excluded_actual_identity_changes_fail_closed(receipt, target):
    run = receipt.observed.planner_run
    if target == "request":
        run = replace(run, decision=replace(run.decision, request_id="wrong-request"))
    elif target == "decision":
        run = replace(run, decision=replace(run.decision, decision_id="wrong-decision"))
    elif target == "rationale":
        run = replace(run, rationale=replace(run.rationale, rationale_id="wrong-rationale"))
    else:
        run = replace(run, run_record=replace(run.run_record, run_id="wrong-run"))
    assert run.decision.verify_content_hash()
    assert run.rationale.verify_content_hash()
    assert run.run_record.verify_content_hash()
    kwargs = _persist_kwargs(receipt)
    kwargs["observed_run"] = replace(receipt.observed, planner_run=run)
    with pytest.raises(ValueError, match="identity"):
        await binding_service.persist_observed_planner_run_decision(**kwargs)
    _assert_only_registration(receipt)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    (
        ("predecision_registration_established", False),
        ("planning_authorized", True),
        ("planning_utility_supported", None),
        ("candidate_authority_modified", True),
    ),
)
async def test_unproven_or_elevated_in_memory_receipt_is_rejected(receipt, field, value):
    kwargs = _persist_kwargs(receipt)
    kwargs["observed_run"] = replace(receipt.observed, **{field: value})
    with pytest.raises(binding_service.PlanningUtilityDecisionBindingError, match="receipt"):
        await binding_service.persist_observed_planner_run_decision(**kwargs)
    _assert_only_registration(receipt)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", (AuditArtifactKind.PLANNER_DECISION, BINDING_KIND))
async def test_missing_database_time_rolls_back_whole_binding_transaction(
    receipt, monkeypatch, kind
):
    original_get = receipt.repository.get

    async def missing_time(**kwargs):
        record = await original_get(**kwargs)
        return (
            replace(record, persisted_at=None)
            if record and record.artifact_kind == kind
            else record
        )

    monkeypatch.setattr(receipt.repository, "get", missing_time)
    with pytest.raises(binding_service.PlanningUtilityDecisionBindingError, match="database"):
        await _completed(receipt)
    _assert_only_registration(receipt)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    (
        ("predecision_registration_established", False),
        ("planning_authorized", True),
        ("utility_endpoint_preregistered", True),
        ("causal_attribution_established", True),
        ("execution_binding_established", True),
    ),
)
async def test_rehashed_durable_binding_cannot_add_authority_or_retroactive_endpoint(
    receipt, field, value
):
    result = await _completed(receipt)
    changed = _rehash(
        replace(result.binding, **{field: value}), DECISION_BINDING_HASH_EXCLUDE_FIELDS
    )
    assert changed.verify_content_hash()
    with Session(receipt.engine) as editor:
        row = editor.execute(
            select(PlanningAuditArtifactRow).where(
                PlanningAuditArtifactRow.artifact_kind == BINDING_KIND.value,
            )
        ).scalar_one()
        row.contract_json = canonical_json(changed)
        row.content_hash = changed.content_hash
        editor.commit()
    with pytest.raises(binding_service.PlanningUtilityDecisionBindingError, match="differs"):
        await binding_service.load_planning_utility_decision(**_load_kwargs(receipt))
    assert receipt.bridge.in_transaction() is False


@pytest.mark.asyncio
async def test_hash_excluded_request_id_tampering_is_rejected_on_restore(receipt):
    result = await _completed(receipt)
    changed = replace(result.planner_run.decision, request_id="another-request")
    assert changed.verify_content_hash()
    assert restore_utility_contract(canonical_json(changed), PlannerDecision) == changed
    with Session(receipt.engine) as editor:
        row = editor.execute(
            select(PlanningAuditArtifactRow).where(
                PlanningAuditArtifactRow.artifact_kind == AuditArtifactKind.PLANNER_DECISION.value,
            )
        ).scalar_one()
        row.contract_json = canonical_json(changed)
        editor.commit()
    with pytest.raises(ValueError, match="identity"):
        await binding_service.load_planning_utility_decision(**_load_kwargs(receipt))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    (
        AuditArtifactKind.PLANNER_DECISION,
        AuditArtifactKind.PROSPECTIVE_VALIDATION_EVIDENCE,
    ),
)
async def test_missing_exact_source_is_unknown_and_never_repaired_by_reexecution(
    receipt, monkeypatch, kind
):
    await _completed(receipt)
    with Session(receipt.engine) as editor:
        row = editor.execute(
            select(PlanningAuditArtifactRow).where(
                PlanningAuditArtifactRow.artifact_kind == kind.value,
            )
        ).scalar_one()
        editor.delete(row)
        editor.commit()

    def no_new_decision(**kwargs):
        pytest.fail("Missing sources cannot be repaired by issuing another decision.")

    monkeypatch.setattr(observation_service.planner, "make_auditable_planner_run", no_new_decision)
    with pytest.raises(binding_service.PlanningUtilityDecisionBindingError, match="missing"):
        await binding_service.load_planning_utility_decision(**_load_kwargs(receipt))
    assert receipt.bridge.in_transaction() is False


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("persist", "load"))
@pytest.mark.parametrize("problem", ("different_session", "existing_transaction"))
async def test_transaction_ownership_guard_preserves_callers_transaction(
    receipt, operation, problem
):
    kwargs = _persist_kwargs(receipt) if operation == "persist" else _load_kwargs(receipt)
    if problem == "different_session":
        kwargs["session"] = SimpleNamespace(in_transaction=lambda: False)
    else:
        await receipt.bridge.execute(select(PlanningAuditArtifactRow))
    calls, commits, rollbacks = (
        receipt.bridge.execute_count,
        receipt.bridge.commit_count,
        receipt.bridge.rollback_count,
    )
    function = (
        binding_service.persist_observed_planner_run_decision
        if operation == "persist"
        else binding_service.load_planning_utility_decision
    )
    with pytest.raises(RuntimeError, match="session"):
        await function(**kwargs)
    assert receipt.bridge.execute_count == calls
    assert receipt.bridge.commit_count == commits
    assert receipt.bridge.rollback_count == rollbacks
    assert receipt.bridge.in_transaction() is (problem == "existing_transaction")
    if receipt.bridge.in_transaction():
        await receipt.bridge.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ("created_only", "different_actual_time"))
async def test_same_actual_decision_identity_cannot_be_replaced_after_completed_binding(
    receipt, change
):
    first = await _completed(receipt)
    run = receipt.observed.planner_run
    # created_at is excluded from all three hashes but canonical audit
    # contracts remain immutable even when a semantic hash is unchanged.
    later = run.decision.created_at + timedelta(microseconds=1)
    if change == "created_only":
        changed = replace(run, decision=replace(run.decision, created_at=later))
        error, message = binding_service.PlanningUtilityDecisionBindingError, "inputs"
    else:
        changed = observation_service.planner.make_auditable_planner_run(
            context=receipt.kwargs["context"],
            request=receipt.kwargs["request"],
            run_id=run.run_record.run_id,
            decision_id=run.decision.decision_id,
            rationale_id=run.rationale.rationale_id,
            decision_time=later,
            created_at=later,
        )
        error, message = AuditArtifactConflictError, "Immutable"
    kwargs = _persist_kwargs(receipt)
    kwargs["observed_run"] = replace(receipt.observed, planner_run=changed)
    with pytest.raises(error, match=message):
        await binding_service.persist_observed_planner_run_decision(**kwargs)
    loaded = await binding_service.load_planning_utility_decision(**_load_kwargs(receipt))
    assert loaded.binding == first.binding


@pytest.mark.asyncio
async def test_pure_builder_preserves_missing_action_without_claiming_observed_execution(receipt):
    kwargs = _pure_kwargs(receipt)
    decision = _rehash(
        replace(
            kwargs["decision"],
            selected_action=None,
            status=PlannerDecisionStatus.NO_FEASIBLE_ACTION,
        ),
        PLANNER_DECISION_HASH_EXCLUDE_FIELDS,
    )
    rationale = _rehash(
        replace(
            kwargs["rationale"],
            decision_hash=decision.content_hash,
            selected_action_id=None,
            decision_status=decision.status.value,
        ),
        RATIONALE_HASH_EXCLUDE_FIELDS,
    )
    run_record = _rehash(
        replace(
            kwargs["run_record"],
            decision_hash=decision.content_hash,
            rationale_hash=rationale.content_hash,
        ),
        RUN_RECORD_HASH_EXCLUDE_FIELDS,
    )
    hashes = {
        AuditArtifactKind.PLANNER_DECISION: decision.content_hash,
        AuditArtifactKind.DECISION_RATIONALE: rationale.content_hash,
        AuditArtifactKind.PLANNER_RUN_RECORD: run_record.content_hash,
    }
    kwargs.update(
        decision=decision,
        rationale=rationale,
        run_record=run_record,
        artifact_refs=tuple(
            replace(ref, content_hash=hashes.get(ref.artifact_kind, ref.content_hash))
            for ref in kwargs["artifact_refs"]
        ),
    )
    binding = build_planning_utility_decision_binding(**kwargs)
    assert binding.selected_action is None
    assert binding.decision_status == PlannerDecisionStatus.NO_FEASIBLE_ACTION
    assert binding.predecision_registration_established is False
    assert binding.execution_binding_established is False
    assert binding.planning_utility_supported is False
    assert binding.verify_content_hash()


@pytest.mark.asyncio
async def test_same_action_id_with_different_parameters_is_not_the_registered_action(receipt):
    kwargs = _pure_kwargs(receipt)
    selected = kwargs["decision"].selected_action
    assert selected is not None
    decision = _rehash(
        replace(
            kwargs["decision"],
            selected_action=replace(
                selected,
                parameters=(("unregistered_parameter", "different"),),
            ),
        ),
        PLANNER_DECISION_HASH_EXCLUDE_FIELDS,
    )
    kwargs["decision"] = decision
    with pytest.raises(ValueError, match="frozen candidate"):
        build_planning_utility_decision_binding(**kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation", ("extra", "missing", "bool_as_int", "naive_time", "tuple_arity")
)
async def test_strict_contract_restore_rejects_ambiguous_shapes_and_types(receipt, mutation):
    binding = build_planning_utility_decision_binding(**_pure_kwargs(receipt))
    assert (
        restore_utility_contract(canonical_json(binding), PlanningUtilityDecisionBinding) == binding
    )
    data = json.loads(canonical_json(binding))
    if mutation == "extra":
        data["unexpected"] = False
    elif mutation == "missing":
        del data["decision_id"]
    elif mutation == "bool_as_int":
        data["shadow_only"] = 1
    elif mutation == "naive_time":
        data["decision_time"] = "2026-10-22T01:02:03"
    else:
        data["selected_action"]["parameters"] = [["key", "value", "extra"]]
    with pytest.raises(ValueError):
        restore_utility_contract(canonical_json(data), PlanningUtilityDecisionBinding)
