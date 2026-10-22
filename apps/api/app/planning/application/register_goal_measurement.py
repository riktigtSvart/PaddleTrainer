"""Commit scalar source rows and their immutable registration together."""

from dataclasses import dataclass
from datetime import UTC, datetime

from ..domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from ..domain.common.time import to_utc
from ..domain.goals.measurement_registration import (
    GOAL_MEASUREMENT_SCHEMA,
    GoalMeasurementProposal,
    GoalMeasurementRegistration,
    build_goal_measurement_registration,
    goal_measurement_id,
)
from ..domain.goals.protocol import require_typed
from ..domain.persistence.audit import AuditArtifactKind, AuditArtifactSaveStatus
from ..domain.planning_utility.decision_binding import restore_utility_contract
from . import register_goal_protocol as goals
from .persist_audit import _record

MEASUREMENT_KIND = AuditArtifactKind.GOAL_MEASUREMENT_REGISTRATION


class GoalMeasurementRegistrationError(RuntimeError):
    pass


class GoalMeasurementRegistrationNotFound(LookupError):
    pass


@dataclass(frozen=True)
class DurableGoalMeasurement:
    artifact: GoalMeasurementRegistration
    durable_available_at: datetime
    reused_registration: bool
    registration_committed: bool
    measurement_schedule_preregistered: bool = True
    physiological_adaptation_established: bool = False
    planning_utility_supported: bool = False
    planning_authorized: bool = False


def _utc_now():
    return datetime.now(UTC)


async def _load(*, athlete_id, artifact_id, available_by, audit_repository):
    record = await audit_repository.get(artifact_kind=MEASUREMENT_KIND, artifact_id=artifact_id)
    if record is None:
        raise GoalMeasurementRegistrationNotFound("Committed goal measurement was not found.")
    artifact = restore_utility_contract(record.contract_json, GoalMeasurementRegistration)
    require_typed(artifact, GoalMeasurementRegistration)
    if (
        record.artifact_kind != MEASUREMENT_KIND
        or record.artifact_id != artifact_id
        or artifact.artifact_id != artifact_id
        or record.athlete_id != athlete_id
        or artifact.athlete_id != athlete_id
        or record.schema_version != GOAL_MEASUREMENT_SCHEMA
        or artifact.schema_version != GOAL_MEASUREMENT_SCHEMA
        or record.content_hash_algorithm != CONTENT_HASH_ALGORITHM
        or record.content_hash != artifact.content_hash
        or canonical_json(artifact) != record.contract_json
        or to_utc(record.created_at, field_name="record.created_at") != artifact.created_at
        or record.persisted_at is None
        or not artifact.created_at
        <= to_utc(record.persisted_at, field_name="record.persisted_at")
        <= available_by
    ):
        raise GoalMeasurementRegistrationError(
            "Stored goal measurement identity or chronology differs."
        )
    protocol, parent = await goals._load(
        audit_repository=audit_repository,
        athlete_id=athlete_id,
        kind=goals.MESO_KIND,
        artifact_id=artifact.protocol_source.artifact_id,
        available_by=available_by,
        cache={},
        visiting=set(),
    )
    if goals._reference(parent) != artifact.protocol_source:
        raise GoalMeasurementRegistrationError("Frozen measurement protocol source changed.")
    replay = build_goal_measurement_registration(
        athlete_id=athlete_id,
        proposal=artifact.proposal,
        protocol=protocol,
        protocol_source=artifact.protocol_source,
        created_at=artifact.created_at,
    )
    if canonical_json(replay) != record.contract_json:
        raise GoalMeasurementRegistrationError(
            "Goal measurement does not replay from its exact inputs."
        )
    return artifact, record


async def register_goal_measurement(
    *, athlete_id, proposal, measurement_repository, audit_repository, session
):
    require_typed(proposal, GoalMeasurementProposal)
    identity = goal_measurement_id(athlete_id, proposal.client_request_id)
    goals._require_session(audit_repository, session, measurement_repository)
    try:
        existing = await audit_repository.get(artifact_kind=MEASUREMENT_KIND, artifact_id=identity)
        if existing is not None:
            artifact, record = await _load(
                athlete_id=athlete_id,
                artifact_id=identity,
                available_by=_utc_now(),
                audit_repository=audit_repository,
            )
            if artifact.proposal != proposal:
                raise GoalMeasurementRegistrationError(
                    "Measurement request identity was reused with different intent."
                )
            await goals._rollback(session)
            return DurableGoalMeasurement(artifact, record.persisted_at, True, True)
        protocol, parent = await goals._load(
            audit_repository=audit_repository,
            athlete_id=athlete_id,
            kind=goals.MESO_KIND,
            artifact_id=proposal.protocol_reference.artifact_id,
            available_by=_utc_now(),
            cache={},
            visiting=set(),
        )
        artifact = build_goal_measurement_registration(
            athlete_id=athlete_id,
            proposal=proposal,
            protocol=protocol,
            protocol_source=goals._reference(parent),
            created_at=_utc_now(),
        )
        await measurement_repository.save(artifact)
        candidate = _record(
            artifact_kind=MEASUREMENT_KIND,
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
            or saved.artifact_kind != MEASUREMENT_KIND
            or saved.artifact_id != identity
            or saved.content_hash != artifact.content_hash
        ):
            raise GoalMeasurementRegistrationError("Measurement audit save result differs.")
        verified, record = await _load(
            athlete_id=athlete_id,
            artifact_id=identity,
            available_by=_utc_now(),
            audit_repository=audit_repository,
        )
        if canonical_json(verified) != candidate.contract_json:
            raise GoalMeasurementRegistrationError("Measurement audit read-back differs.")
        await measurement_repository.verify(verified)
        await session.commit()
        if session.in_transaction() is not False:
            raise GoalMeasurementRegistrationError(
                "Measurement commit did not close its transaction."
            )
        return DurableGoalMeasurement(verified, record.persisted_at, False, True)
    except BaseException:
        await goals._rollback(session)
        raise


async def load_goal_measurement(
    *, athlete_id, artifact_id, available_by, audit_repository, session
):
    available = to_utc(available_by, field_name="available_by")
    if available > _utc_now():
        raise GoalMeasurementRegistrationError(
            "A future measurement availability cutoff cannot be attested."
        )
    goals._require_session(audit_repository, session)
    try:
        artifact, record = await _load(
            athlete_id=athlete_id,
            artifact_id=artifact_id,
            available_by=available,
            audit_repository=audit_repository,
        )
        return DurableGoalMeasurement(artifact, record.persisted_at, True, True)
    finally:
        await goals._rollback(session)
