"""Own one census/assessment transaction and replay its frozen historical inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ..domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from ..domain.common.time import to_utc
from ..domain.goals.assessment import (
    GOAL_ASSESSMENT_SCHEMA,
    GoalMeasurementCensus,
    MesocycleGoalAssessment,
    build_mesocycle_goal_assessment,
    goal_assessment_id,
)
from ..domain.goals.protocol import GoalVersionReference, require_typed
from ..domain.persistence.audit import AuditArtifactKind, AuditArtifactSaveStatus
from ..domain.planning_utility.decision_binding import restore_utility_contract
from . import register_goal_protocol as goals
from .persist_audit import _record

ASSESSMENT_KIND = AuditArtifactKind.MESOCYCLE_GOAL_ASSESSMENT


class GoalAssessmentError(RuntimeError):
    pass


class GoalAssessmentNotFound(LookupError):
    pass


@dataclass(frozen=True)
class DurableGoalAssessment:
    artifact: MesocycleGoalAssessment
    durable_available_at: datetime
    reused_assessment: bool
    assessment_committed: bool
    measurement_schedule_preregistered: bool = True
    physiological_adaptation_established: bool = False
    planning_utility_supported: bool = False
    planning_authorized: bool = False


def _utc_now():
    return datetime.now(UTC)


def _restore(record, *, athlete_id, artifact_id, available_by):
    artifact = restore_utility_contract(record.contract_json, MesocycleGoalAssessment)
    require_typed(artifact, MesocycleGoalAssessment)
    if (
        record.artifact_kind != ASSESSMENT_KIND
        or record.artifact_id != artifact_id
        or artifact.artifact_id != artifact_id
        or record.athlete_id != athlete_id
        or artifact.athlete_id != athlete_id
        or record.schema_version != GOAL_ASSESSMENT_SCHEMA
        or artifact.schema_version != GOAL_ASSESSMENT_SCHEMA
        or record.content_hash_algorithm != CONTENT_HASH_ALGORITHM
        or artifact.content_hash_algorithm != CONTENT_HASH_ALGORITHM
        or record.content_hash != artifact.content_hash
        or not artifact.verify_content_hash()
        or canonical_json(artifact) != record.contract_json
        or to_utc(record.created_at, field_name="record.created_at") != artifact.created_at
        or record.persisted_at is None
    ):
        raise GoalAssessmentError(
            "Stored goal assessment identity, canonical payload or hash differs."
        )
    persisted = to_utc(record.persisted_at, field_name="record.persisted_at")
    if not (artifact.created_at <= persisted <= available_by):
        raise GoalAssessmentError("Goal assessment durable availability chronology differs.")
    return artifact


async def _load(*, athlete_id, artifact_id, available_by, audit_repository):
    record = await audit_repository.get(artifact_kind=ASSESSMENT_KIND, artifact_id=artifact_id)
    if record is None:
        raise GoalAssessmentNotFound("Committed goal assessment was not found.")
    artifact = _restore(
        record, athlete_id=athlete_id, artifact_id=artifact_id, available_by=available_by
    )
    ref = artifact.protocol_source
    protocol, protocol_record = await goals._load(
        audit_repository=audit_repository,
        athlete_id=athlete_id,
        kind=goals.MESO_KIND,
        artifact_id=ref.artifact_id,
        available_by=available_by,
        cache={},
        visiting=set(),
    )
    if goals._reference(protocol_record) != ref:
        raise GoalAssessmentError("Frozen mesocycle goal protocol source changed.")
    replay = build_mesocycle_goal_assessment(
        protocol=protocol,
        protocol_source=ref,
        activity_cutoff_at=artifact.activity_cutoff_at,
        census=artifact.census,
        created_at=artifact.created_at,
    )
    if canonical_json(replay) != record.contract_json:
        raise GoalAssessmentError("Goal assessment does not replay from its exact frozen sources.")
    return artifact, record


async def assess_mesocycle_goal_protocol(
    *,
    athlete_id,
    protocol_reference,
    activity_cutoff_at,
    source_repository,
    audit_repository,
    session,
):
    """No caller-selected outcomes, roles, thresholds, units or uncertainty overrides.

    activity_cutoff_at limits event times. Mutable source rows are captured now;
    this operation does not attest their historical availability at that cutoff.
    An identical slot always reuses the first committed census, including gaps.
    """
    require_typed(protocol_reference, GoalVersionReference)
    cutoff = to_utc(activity_cutoff_at, field_name="activity_cutoff_at")
    if cutoff > _utc_now():
        raise GoalAssessmentError("A future activity cutoff cannot be assessed.")
    identity = goal_assessment_id(athlete_id, protocol_reference.artifact_id, cutoff)
    goals._require_session(audit_repository, session, source_repository)
    try:
        existing = await audit_repository.get(artifact_kind=ASSESSMENT_KIND, artifact_id=identity)
        if existing is not None:
            artifact, record = await _load(
                athlete_id=athlete_id,
                artifact_id=identity,
                available_by=_utc_now(),
                audit_repository=audit_repository,
            )
            if artifact.protocol_source.content_hash != protocol_reference.content_hash:
                raise GoalAssessmentError("Assessment slot was reused for a different protocol.")
            await goals._rollback(session)
            return DurableGoalAssessment(artifact, record.persisted_at, True, True)
        protocol, protocol_record = await goals._load(
            audit_repository=audit_repository,
            athlete_id=athlete_id,
            kind=goals.MESO_KIND,
            artifact_id=protocol_reference.artifact_id,
            available_by=_utc_now(),
            cache={},
            visiting=set(),
        )
        if protocol.content_hash != protocol_reference.content_hash:
            raise GoalAssessmentError("Requested protocol content hash differs.")
        started = _utc_now()
        start = min(e.baseline_window.starts_at for e in protocol.proposal.endpoints)
        end = min(cutoff, max(e.followup_window.ends_at for e in protocol.proposal.endpoints))
        if cutoff < start:
            raise GoalAssessmentError("Activity cutoff precedes the first measurement window.")
        sources = await source_repository.capture(
            athlete_id=athlete_id,
            starts_at=start,
            ends_at=end,
            recorded_before=started,
        )
        census = GoalMeasurementCensus(athlete_id, start, end, started, _utc_now(), sources)
        artifact = build_mesocycle_goal_assessment(
            protocol=protocol,
            protocol_source=goals._reference(protocol_record),
            activity_cutoff_at=cutoff,
            census=census,
            created_at=_utc_now(),
        )
        candidate = _record(
            artifact_kind=ASSESSMENT_KIND,
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
            or saved.artifact_kind != ASSESSMENT_KIND
            or saved.artifact_id != identity
            or saved.content_hash != artifact.content_hash
        ):
            raise GoalAssessmentError("Goal assessment repository save result differs.")
        verified, stored = await _load(
            athlete_id=athlete_id,
            artifact_id=identity,
            available_by=_utc_now(),
            audit_repository=audit_repository,
        )
        if canonical_json(verified) != candidate.contract_json:
            raise GoalAssessmentError("Goal assessment repository read-back differs.")
        await session.commit()
        if session.in_transaction() is not False:
            raise GoalAssessmentError("Goal assessment commit did not close its transaction.")
        return DurableGoalAssessment(verified, stored.persisted_at, False, True)
    except BaseException:
        await goals._rollback(session)
        raise


async def load_mesocycle_goal_assessment(
    *,
    athlete_id,
    artifact_id,
    available_by,
    audit_repository,
    session,
):
    available = to_utc(available_by, field_name="available_by")
    if available > _utc_now():
        raise GoalAssessmentError("A future assessment availability cutoff cannot be attested.")
    goals._require_session(audit_repository, session)
    try:
        artifact, record = await _load(
            athlete_id=athlete_id,
            artifact_id=artifact_id,
            available_by=available,
            audit_repository=audit_repository,
        )
        return DurableGoalAssessment(artifact, record.persisted_at, True, True)
    finally:
        await goals._rollback(session)
