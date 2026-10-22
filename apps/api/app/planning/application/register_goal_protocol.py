"""Commit explicit cycle-goal intent before its scheduled measurements.

New registrations capture current mutable period inputs. Retry and historical
load replay the original immutable inputs; they never recapture today's goals.
No outcome, planner, plan mutation or athlete-data ingestion is invoked here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from ..domain.common.refs import SourceSnapshotRef
from ..domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from ..domain.common.time import to_utc
from ..domain.goals.protocol import (
    MACROCYCLE_PLAN_SCHEMA,
    MESOCYCLE_PROTOCOL_SCHEMA,
    DurableGoalSourceReference,
    MacrocycleCapabilityPlan,
    MacrocyclePlanProposal,
    MesocycleGoalProtocol,
    MesocycleProtocolProposal,
    build_macrocycle_capability_plan,
    build_mesocycle_goal_protocol,
    goal_artifact_id,
    require_typed,
)
from ..domain.persistence.audit import AuditArtifactKind, AuditArtifactSaveStatus
from ..domain.planning_utility.decision_binding import restore_utility_contract
from .persist_audit import _record

GOAL_VERSION_CHAIN_LIMIT = 64
GOAL_DEPENDENCY_DEPTH_LIMIT = 2 * GOAL_VERSION_CHAIN_LIMIT
MACRO_KIND = AuditArtifactKind.MACROCYCLE_CAPABILITY_PLAN
MESO_KIND = AuditArtifactKind.MESOCYCLE_GOAL_PROTOCOL


class CycleGoalProtocolError(RuntimeError):
    pass


class CycleGoalArtifactNotFound(LookupError):
    pass


@dataclass(frozen=True)
class DurableCycleGoalRegistration:
    artifact: MacrocycleCapabilityPlan | MesocycleGoalProtocol
    durable_available_at: datetime
    reused_registration: bool
    registration_committed: bool
    measurement_schedule_preregistered: bool
    comparative_utility_endpoint_preregistered: bool = False
    planning_utility_supported: bool = False
    planning_authorized: bool = False


def _utc_now():
    return datetime.now(UTC)


def _require_session(audit_repository, session, source_repository=None):
    if session is None or getattr(audit_repository, "session", None) is not session:
        raise CycleGoalProtocolError(
            "Goal registration requires the exact audit repository session."
        )
    inspect = getattr(session, "in_transaction", None)
    if not callable(inspect) or inspect() is not False:
        raise CycleGoalProtocolError("Goal registration requires a known fresh session.")
    if source_repository is not None and getattr(source_repository, "session", None) is not session:
        raise CycleGoalProtocolError(
            "Goal source and audit repositories must share the same session."
        )


def _reference(record):
    return DurableGoalSourceReference(
        record.artifact_kind,
        record.artifact_id,
        record.content_hash,
        sha256(record.contract_json.encode("utf-8")).hexdigest(),
        record.persisted_at,
    )


async def _rollback(session):
    await session.rollback()
    if session.in_transaction() is not False:
        raise CycleGoalProtocolError("Goal read transaction did not close after rollback.")


def _check_procedure_revision(previous, current):
    if previous is None:
        return
    definitions = {
        (e.procedure.protocol_key, e.procedure.protocol_version): e.procedure
        for e in previous.proposal.endpoints
    }
    for endpoint in current.proposal.endpoints:
        key = (endpoint.procedure.protocol_key, endpoint.procedure.protocol_version)
        if key in definitions and endpoint.procedure != definitions[key]:
            raise CycleGoalProtocolError(
                "A changed measurement procedure requires a new procedure version."
            )


def _restore(record, *, athlete_id, kind, artifact_id, available_by):
    cls, schema = {
        MACRO_KIND: (MacrocycleCapabilityPlan, MACROCYCLE_PLAN_SCHEMA),
        MESO_KIND: (MesocycleGoalProtocol, MESOCYCLE_PROTOCOL_SCHEMA),
    }[kind]
    artifact = restore_utility_contract(record.contract_json, cls)
    require_typed(artifact, cls)
    if (
        record.artifact_kind != kind
        or record.artifact_id != artifact_id
        or artifact.artifact_id != artifact_id
        or record.athlete_id != athlete_id
        or artifact.athlete_id != athlete_id
        or record.schema_version != schema
        or artifact.schema_version != schema
        or record.content_hash_algorithm != CONTENT_HASH_ALGORITHM
        or artifact.content_hash_algorithm != CONTENT_HASH_ALGORITHM
        or record.content_hash != artifact.content_hash
        or not artifact.verify_content_hash()
        or canonical_json(artifact) != record.contract_json
        or to_utc(record.created_at, field_name="record.created_at") != artifact.created_at
    ):
        raise CycleGoalProtocolError(
            "Stored cycle-goal identity, canonical contract or hash differs."
        )
    if record.persisted_at is None:
        raise CycleGoalProtocolError("Cycle-goal database persistence time is unknown.")
    persisted = to_utc(record.persisted_at, field_name="record.persisted_at")
    if not (artifact.created_at <= persisted <= available_by):
        raise CycleGoalProtocolError("Cycle-goal durable availability chronology differs.")
    if kind == MESO_KIND and any(
        persisted >= endpoint.baseline_window.starts_at for endpoint in artifact.proposal.endpoints
    ):
        raise CycleGoalProtocolError("Goal protocol was not durable before every baseline window.")
    return artifact


async def _load(
    *, audit_repository, athlete_id, kind, artifact_id, available_by, cache, visiting, depth=0
):
    if kind not in {MACRO_KIND, MESO_KIND} or depth >= GOAL_DEPENDENCY_DEPTH_LIMIT:
        raise CycleGoalProtocolError("Unsupported or incomplete cycle-goal version chain.")
    key = (kind, artifact_id)
    if key in visiting:
        raise CycleGoalProtocolError("Cyclic goal provenance.")
    if key in cache:
        return cache[key]
    record = await audit_repository.get(artifact_kind=kind, artifact_id=artifact_id)
    if record is None:
        raise CycleGoalArtifactNotFound("Committed cycle-goal source was not found.")
    artifact = _restore(
        record, athlete_id=athlete_id, kind=kind, artifact_id=artifact_id, available_by=available_by
    )
    visiting.add(key)
    previous_artifact = None
    for ref in (artifact.previous_source,):
        if ref is not None:
            previous_artifact, parent_record = await _load(
                audit_repository=audit_repository,
                athlete_id=athlete_id,
                kind=ref.artifact_kind,
                artifact_id=ref.artifact_id,
                available_by=available_by,
                cache=cache,
                visiting=visiting,
                depth=depth + 1,
            )
            if _reference(parent_record) != ref:
                raise CycleGoalProtocolError("Frozen previous goal version changed.")
    if kind == MACRO_KIND:
        replay = build_macrocycle_capability_plan(
            athlete_id=athlete_id,
            proposal=artifact.proposal,
            sources=artifact.sources,
            previous_source=artifact.previous_source,
            created_at=artifact.created_at,
        )
    else:
        _check_procedure_revision(previous_artifact, artifact)
        ref = artifact.macrocycle_source
        macro, parent_record = await _load(
            audit_repository=audit_repository,
            athlete_id=athlete_id,
            kind=MACRO_KIND,
            artifact_id=ref.artifact_id,
            available_by=available_by,
            cache=cache,
            visiting=visiting,
            depth=depth + 1,
        )
        if _reference(parent_record) != ref:
            raise CycleGoalProtocolError("Frozen macrocycle goal source changed.")
        replay = build_mesocycle_goal_protocol(
            athlete_id=athlete_id,
            proposal=artifact.proposal,
            macrocycle_plan=macro,
            macrocycle_source=ref,
            sources=artifact.sources,
            previous_source=artifact.previous_source,
            created_at=artifact.created_at,
        )
    if canonical_json(replay) != record.contract_json:
        raise CycleGoalProtocolError("Cycle-goal contract does not replay from its exact sources.")
    visiting.remove(key)
    cache[key] = (artifact, record)
    return artifact, record


async def _register(*, athlete_id, proposal, kind, source_repository, audit_repository, session):
    expected = MacrocyclePlanProposal if kind == MACRO_KIND else MesocycleProtocolProposal
    require_typed(proposal, expected)
    period_id = (
        proposal.macrocycle_period_id if kind == MACRO_KIND else proposal.mesocycle_period_id
    )
    identity = goal_artifact_id(kind, athlete_id, period_id, proposal.revision)
    if proposal.revision > GOAL_VERSION_CHAIN_LIMIT:
        raise CycleGoalProtocolError("Goal version chain limit requires a later schema migration.")
    _require_session(audit_repository, session, source_repository)
    try:
        cache, visiting = {}, set()
        existing = await audit_repository.get(artifact_kind=kind, artifact_id=identity)
        if existing is not None:
            artifact, record = await _load(
                audit_repository=audit_repository,
                athlete_id=athlete_id,
                kind=kind,
                artifact_id=identity,
                available_by=_utc_now(),
                cache=cache,
                visiting=visiting,
            )
            if artifact.proposal != proposal:
                raise CycleGoalProtocolError(
                    "Immutable goal version was reused for a different intent."
                )
            await _rollback(session)
            return DurableCycleGoalRegistration(
                artifact, record.persisted_at, True, True, kind == MESO_KIND
            )
        previous = None
        previous_artifact = None
        if proposal.supersedes is not None:
            previous_artifact, record = await _load(
                audit_repository=audit_repository,
                athlete_id=athlete_id,
                kind=kind,
                artifact_id=proposal.supersedes.artifact_id,
                available_by=_utc_now(),
                cache=cache,
                visiting=visiting,
            )
            previous = _reference(record)
        if kind == MACRO_KIND:
            sources = await source_repository.capture(
                athlete_id=athlete_id,
                macrocycle_period_id=proposal.macrocycle_period_id,
            )
            artifact = build_macrocycle_capability_plan(
                athlete_id=athlete_id,
                proposal=proposal,
                sources=sources,
                previous_source=previous,
                created_at=_utc_now(),
            )
        else:
            macro, record = await _load(
                audit_repository=audit_repository,
                athlete_id=athlete_id,
                kind=MACRO_KIND,
                artifact_id=proposal.macrocycle_plan.artifact_id,
                available_by=_utc_now(),
                cache=cache,
                visiting=visiting,
            )
            sources = await source_repository.capture(
                athlete_id=athlete_id,
                macrocycle_period_id=macro.proposal.macrocycle_period_id,
            )
            artifact = build_mesocycle_goal_protocol(
                athlete_id=athlete_id,
                proposal=proposal,
                macrocycle_plan=macro,
                macrocycle_source=_reference(record),
                sources=sources,
                previous_source=previous,
                created_at=_utc_now(),
            )
            _check_procedure_revision(previous_artifact, artifact)
        candidate = _record(
            artifact_kind=kind,
            artifact_id=identity,
            athlete_id=athlete_id,
            schema_version=artifact.schema_version,
            created_at=artifact.created_at,
            artifact=artifact,
        )
        saved = await audit_repository.save(candidate)
        if (
            saved.status
            not in {AuditArtifactSaveStatus.CREATED, AuditArtifactSaveStatus.ALREADY_PRESENT}
            or saved.artifact_kind != kind
            or saved.artifact_id != identity
            or saved.content_hash != artifact.content_hash
        ):
            raise CycleGoalProtocolError("Goal repository save result differs.")
        verified, stored = await _load(
            audit_repository=audit_repository,
            athlete_id=athlete_id,
            kind=kind,
            artifact_id=identity,
            available_by=_utc_now(),
            cache={},
            visiting=set(),
        )
        if canonical_json(verified) != candidate.contract_json:
            raise CycleGoalProtocolError("Goal repository read-back differs.")
        await session.commit()
        if session.in_transaction() is not False:
            raise CycleGoalProtocolError("Goal registration commit did not close its transaction.")
        return DurableCycleGoalRegistration(
            verified, stored.persisted_at, False, True, kind == MESO_KIND
        )
    except BaseException:
        await _rollback(session)
        raise


async def register_macrocycle_capability_plan(
    *, athlete_id, proposal, source_repository, audit_repository, session
):
    return await _register(
        athlete_id=athlete_id,
        proposal=proposal,
        kind=MACRO_KIND,
        source_repository=source_repository,
        audit_repository=audit_repository,
        session=session,
    )


async def register_mesocycle_goal_protocol(
    *, athlete_id, proposal, source_repository, audit_repository, session
):
    return await _register(
        athlete_id=athlete_id,
        proposal=proposal,
        kind=MESO_KIND,
        source_repository=source_repository,
        audit_repository=audit_repository,
        session=session,
    )


async def load_cycle_goal_artifact(
    *, athlete_id, artifact_kind, artifact_id, available_by, audit_repository, session
):
    cutoff = to_utc(available_by, field_name="available_by")
    if cutoff > _utc_now():
        raise CycleGoalProtocolError("A future goal availability cutoff cannot be attested.")
    _require_session(audit_repository, session)
    try:
        artifact, record = await _load(
            audit_repository=audit_repository,
            athlete_id=athlete_id,
            kind=artifact_kind,
            artifact_id=artifact_id,
            available_by=cutoff,
            cache={},
            visiting=set(),
        )
        return DurableCycleGoalRegistration(
            artifact, record.persisted_at, True, True, artifact_kind == MESO_KIND
        )
    finally:
        await _rollback(session)


async def load_mesocycle_goal_context_source(
    *, athlete_id, artifact_id, available_by, audit_repository, session
):
    """Return a verified optional context source; caller must attach it explicitly.

    Existing P2.4A/B schemas and flags are unchanged. This reference does not
    resolve planner goal priority, authorize a workout, or preregister a
    comparative planning-utility experiment.
    """
    loaded = await load_cycle_goal_artifact(
        athlete_id=athlete_id,
        artifact_kind=MESO_KIND,
        artifact_id=artifact_id,
        available_by=available_by,
        audit_repository=audit_repository,
        session=session,
    )
    artifact = loaded.artifact
    return SourceSnapshotRef(
        domain="MESOCYCLE_GOAL_PROTOCOL",
        object_id=artifact.artifact_id,
        object_version=artifact.schema_version,
        as_of=artifact.created_at,
        information_cutoff_at=artifact.created_at,
        available_at=loaded.durable_available_at,
        content_hash=artifact.content_hash,
    )
