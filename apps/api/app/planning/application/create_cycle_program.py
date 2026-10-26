"""Create a complete calendar graph and its immutable receipt in one transaction.

Retries restore the original registration, including its original timezone and
calendar reference. They never recapture defaults, repair or overwrite periods.
Competition refinements append history and never retime registered periods.
"""

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.models.entities import PeriodType, TrainingPeriod, User
from app.schemas.planning_cycles import CompetitionRevisionInput, CycleProgramInput

from ..domain import cycle_program as domain
from ..domain import cycle_program_context as context
from ..domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from ..domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveStatus,
)
from . import register_goal_protocol as transactions

PROGRAM = AuditArtifactKind.CYCLE_PROGRAM_REGISTRATION
EVENTS = AuditArtifactKind.CYCLE_COMPETITION_REVISION


class CycleStorageError(RuntimeError):
    pass


class CycleNotFound(LookupError):
    pass


def _now():
    return datetime.now(UTC)


def _same_reference(artifact, requested):
    if domain.reference(artifact) != requested:
        raise domain.CycleRuleError("CYCLE_REFERENCE_DIFFERS")


async def _load(repository, owner, kind, identity, *, cache=None, visiting=None):
    cache = {} if cache is None else cache
    visiting = set() if visiting is None else visiting
    key = (kind, identity)
    if key in cache:
        return cache[key]
    if key in visiting or len(visiting) >= 512:
        raise CycleStorageError("Cycle receipt chain is cyclic or too long.")
    visiting.add(key)
    record = await repository.get(artifact_kind=kind, artifact_id=identity)
    if record is None or record.athlete_id != owner:
        raise CycleNotFound("CYCLE_PROGRAM_NOT_FOUND")
    artifact = json.loads(record.contract_json)
    created = datetime.fromisoformat(artifact["created_at"])
    if (
        created.tzinfo is None
        or record.created_at != created
        or record.persisted_at is None
        or record.persisted_at.tzinfo is None
        or record.artifact_kind != kind
        or record.artifact_id != identity
        or record.schema_version != artifact["schema_version"]
        or record.content_hash_algorithm != CONTENT_HASH_ALGORITHM
        or record.content_hash != artifact["content_hash"]
        or artifact["athlete_id"] != owner
        or artifact["artifact_id"] != identity
        or canonical_json(artifact) != record.contract_json
    ):
        raise CycleStorageError("Stored cycle registration metadata differs.")
    if kind == PROGRAM:
        if artifact["schema_version"] not in {
            domain.SCHEMA,
            context.CONTEXT_SCHEMA,
            context.INTAKE_SCHEMA,
        }:
            raise CycleStorageError("Unsupported cycle registration schema.")
        proposal = CycleProgramInput.model_validate(artifact["proposal"]).model_dump()
        continuation = None
        if proposal["continued_from"] is not None:
            continuation, parent = await _load(
                repository,
                owner,
                PROGRAM,
                proposal["continued_from"]["artifact_id"],
                cache=cache,
                visiting=visiting,
            )
            _same_reference(continuation, proposal["continued_from"])
            if parent.persisted_at > created:
                raise CycleStorageError("Continuation predates its durable parent.")
        replay = domain.build_registration(
            proposal,
            athlete_id=owner,
            timezone_name=artifact["timezone_name"],
            created_at=artifact["created_at"],
            calendar_snapshot=artifact["calendar_snapshot"],
            continuation=continuation,
            athlete_snapshot=await athlete_snapshot(
                repository,
                session=None,
                owner=owner,
                proposal=proposal,
                created_at=artifact["created_at"],
                timezone_name=artifact["timezone_name"],
                validate_latest=False,
            ),
        )
    elif kind == EVENTS:
        if artifact["schema_version"] not in {domain.EVENT_SCHEMA, context.CONTEXT_EVENT_SCHEMA}:
            raise CycleStorageError("Unsupported competition revision schema.")
        proposal = CompetitionRevisionInput.model_validate(artifact["proposal"]).model_dump()
        program, base = await _load(
            repository,
            owner,
            PROGRAM,
            proposal["program_reference"]["artifact_id"],
            cache=cache,
            visiting=visiting,
        )
        if base.persisted_at > created:
            raise CycleStorageError("Competition revision predates its program.")
        previous = None
        if proposal["previous_reference"] is not None:
            previous, parent = await _load(
                repository,
                owner,
                EVENTS,
                proposal["previous_reference"]["artifact_id"],
                cache=cache,
                visiting=visiting,
            )
            if parent.persisted_at > created:
                raise CycleStorageError("Competition revision predates its parent.")
        replay = domain.build_competition_revision(
            proposal,
            program=program,
            previous=previous,
            created_at=artifact["created_at"],
        )
    elif kind == AuditArtifactKind.CYCLE_MESOCYCLE_BOUNDARY_REVISION:
        from app.planning.domain import cycle_boundary
        from app.schemas.planning_cycles import BoundaryRevisionInput

        if artifact["schema_version"] != cycle_boundary.SCHEMA:
            raise CycleStorageError("Unsupported boundary revision schema.")
        proposal = BoundaryRevisionInput.model_validate(artifact["proposal"]).model_dump()
        program, base = await _load(
            repository,
            owner,
            PROGRAM,
            proposal["program_reference"]["artifact_id"],
            cache=cache,
            visiting=visiting,
        )
        previous = None
        parents = [base]
        if proposal["previous_reference"]:
            previous, parent = await _load(
                repository,
                owner,
                kind,
                proposal["previous_reference"]["artifact_id"],
                cache=cache,
                visiting=visiting,
            )
            parents.append(parent)
        competition = program
        if proposal["competition_reference"] != domain.reference(program):
            competition, parent = await _load(
                repository,
                owner,
                EVENTS,
                proposal["competition_reference"]["artifact_id"],
                cache=cache,
                visiting=visiting,
            )
            parents.append(parent)
        if any(parent.persisted_at > created for parent in parents):
            raise CycleStorageError("Boundary revision predates a durable parent.")
        replay = cycle_boundary.build(
            proposal,
            program=program,
            previous=previous,
            competition=competition,
            created_at=artifact["created_at"],
            timezone_name=artifact["timezone_name"],
        )
    else:
        raise CycleStorageError("Unsupported cycle receipt kind.")
    if canonical_json(replay) != record.contract_json:
        raise CycleStorageError("Stored cycle receipt does not replay from its inputs.")
    visiting.remove(key)
    cache[key] = (artifact, record)
    return artifact, record


def receipt(artifact, record, *, reused):
    return {
        "identity_scope": "APPLICATION_DEMO_USER",
        "artifact": artifact,
        "durable_available_at": record.persisted_at,
        "reused": reused,
        "committed": True,
        "planning_authorized": False,
        "workouts_created": False,
    }


async def timezone_for(session, owner):
    result = await session.execute(select(User.timezone).where(User.id == UUID(owner)))
    timezone_name = result.scalar_one_or_none()
    if timezone_name is None:
        raise CycleNotFound("CYCLE_CONFIGURED_OWNER_NOT_FOUND")
    return timezone_name


async def _save(repository, artifact, kind):
    record = AuditArtifactRecord(
        artifact_kind=kind,
        artifact_id=artifact["artifact_id"],
        athlete_id=artifact["athlete_id"],
        schema_version=artifact["schema_version"],
        created_at=datetime.fromisoformat(artifact["created_at"]),
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash=artifact["content_hash"],
        contract_json=canonical_json(artifact),
    )
    saved = await repository.save(record)
    if (
        saved.status != AuditArtifactSaveStatus.CREATED
        or saved.artifact_kind != kind
        or saved.artifact_id != artifact["artifact_id"]
        or saved.content_hash != artifact["content_hash"]
    ):
        raise CycleStorageError("Cycle audit insertion was not confirmed.")
    verified, stored = await _load(
        repository, artifact["athlete_id"], kind, artifact["artifact_id"]
    )
    if canonical_json(verified) != record.contract_json:
        raise CycleStorageError("Cycle registration read-back differs.")
    return stored


async def _commit(session):
    await session.commit()
    if session.in_transaction() is not False:
        raise CycleStorageError("Cycle commit did not close its transaction.")


async def create_program(*, owner, proposal, repository, session):
    transactions._require_session(repository, session)
    identity = domain.registration_slot(owner, proposal)
    try:
        existing = await repository.get(artifact_kind=PROGRAM, artifact_id=identity)
        if existing is not None:
            artifact, record = await _load(repository, owner, PROGRAM, identity)
            if artifact["proposal"] != proposal:
                raise domain.CycleRuleError("CYCLE_REQUEST_IDENTITY_CONFLICT")
            await transactions._rollback(session)
            return receipt(artifact, record, reused=True)
        continuation = None
        if proposal["continued_from"] is not None:
            continuation, _ = await _load(
                repository,
                owner,
                PROGRAM,
                proposal["continued_from"]["artifact_id"],
            )
            _same_reference(continuation, proposal["continued_from"])
        from .register_athlete_setup import lock_owner

        if "athlete_context" in proposal:
            await lock_owner(session, owner)
            # A concurrent identical request may have committed while this owner lock was pending.
            committed = await repository.get(artifact_kind=PROGRAM, artifact_id=identity)
            if committed is not None:
                artifact, record = await _load(repository, owner, PROGRAM, identity)
                if artifact["proposal"] != proposal:
                    raise domain.CycleRuleError("CYCLE_REQUEST_IDENTITY_CONFLICT")
                await transactions._rollback(session)
                return receipt(artifact, record, reused=True)
        created_at = _now().isoformat()
        timezone_name = await timezone_for(session, owner)
        snapshot = await athlete_snapshot(
            repository,
            session=session,
            owner=owner,
            proposal=proposal,
            created_at=created_at,
            timezone_name=timezone_name,
            validate_latest=True,
        )
        artifact = domain.build_registration(
            proposal,
            athlete_id=owner,
            timezone_name=timezone_name,
            created_at=created_at,
            continuation=continuation,
            athlete_snapshot=snapshot,
        )
        for period in artifact["periods"]:
            # UUIDs are derived from owner + program + explicit node key. Flush in
            # parent-first order so FK validity never depends on ORM inference.
            session.add(
                TrainingPeriod(
                    id=UUID(period["id"]),
                    user_id=UUID(owner),
                    parent_id=UUID(period["parent_id"]) if period["parent_id"] else None,
                    period_type=PeriodType(period["period_type"]),
                    title=period["title"],
                    start_date=datetime.fromisoformat(period["start_date"]).date(),
                    end_date=datetime.fromisoformat(period["end_date"]).date(),
                    description=proposal["title"],
                    extra_data={
                        "cycle_program_artifact_id": identity,
                        "cycle_program_id": proposal["program_id"],
                        "entry_mode": proposal["mode"],
                        "node_key": period["key"],
                        **(
                            {
                                "cycle_dates_role": "provisional",
                                "planning_basis_version": proposal["planning_basis"]["version"],
                            }
                            if "planning_basis" in proposal
                            else {}
                        ),
                    },
                )
            )
            await session.flush()
        record = await _save(repository, artifact, PROGRAM)
        rows = await session.execute(
            select(TrainingPeriod)
            .where(TrainingPeriod.id.in_([UUID(p["id"]) for p in artifact["periods"]]))
            .execution_options(populate_existing=True)
        )
        actual = {str(r.id): r for r in rows.scalars().all()}
        for expected in artifact["periods"]:
            row = actual.get(expected["id"])
            if (
                row is None
                or str(row.user_id) != owner
                or (str(row.parent_id) if row.parent_id else None) != expected["parent_id"]
                or row.period_type.value != expected["period_type"]
                or row.title != expected["title"]
                or row.start_date.isoformat() != expected["start_date"]
                or row.end_date.isoformat() != expected["end_date"]
                or row.extra_data.get("cycle_program_artifact_id") != identity
            ):
                raise CycleStorageError("Created period read-back differs.")
        await _commit(session)
        return receipt(artifact, record, reused=False)
    except BaseException:
        await transactions._rollback(session)
        raise


async def revise_competitions(*, owner, proposal, repository, session):
    transactions._require_session(repository, session)
    try:
        program, _ = await _load(
            repository, owner, PROGRAM, proposal["program_reference"]["artifact_id"]
        )
        _same_reference(program, proposal["program_reference"])
        from .revise_cycle_boundary import lock_periods

        await lock_periods(session, owner, program)
        identity = domain.slot(
            owner, program["proposal"]["program_id"], revision=proposal["revision"]
        )
        existing = await repository.get(artifact_kind=EVENTS, artifact_id=identity)
        if existing is not None:
            artifact, record = await _load(repository, owner, EVENTS, identity)
            if artifact["proposal"] != proposal:
                raise domain.CycleRuleError("CYCLE_REQUEST_IDENTITY_CONFLICT")
            await transactions._rollback(session)
            return receipt(artifact, record, reused=True)
        previous = None
        if proposal["previous_reference"] is not None:
            previous, _ = await _load(
                repository, owner, EVENTS, proposal["previous_reference"]["artifact_id"]
            )
        artifact = domain.build_competition_revision(
            proposal,
            program=program,
            previous=previous,
            created_at=_now().isoformat(),
        )
        record = await _save(repository, artifact, EVENTS)
        await _commit(session)
        return receipt(artifact, record, reused=False)
    except BaseException:
        await transactions._rollback(session)
        raise


async def load_program(*, owner, identity, repository, session):
    transactions._require_session(repository, session)
    try:
        cache = {}
        artifact, record = await _load(repository, owner, PROGRAM, identity, cache=cache)
        revisions = []
        for number in range(1, 65):
            revision_id = domain.slot(owner, artifact["proposal"]["program_id"], revision=number)
            row = await repository.get(artifact_kind=EVENTS, artifact_id=revision_id)
            if row is None:
                break
            updated, stored = await _load(repository, owner, EVENTS, revision_id, cache=cache)
            revisions.append(receipt(updated, stored, reused=True))
        from .revise_cycle_boundary import head

        boundaries = await head(repository, owner, artifact)
        return {
            "program": receipt(artifact, record, reused=True),
            "competition_revisions": revisions,
            "boundary_revisions": boundaries,
        }
    finally:
        await transactions._rollback(session)


async def athlete_snapshot(
    repository, *, session, owner, proposal, created_at, timezone_name, validate_latest
):
    if "athlete_context" not in proposal:
        return None
    from ..domain import athlete_setup as setup_domain
    from . import register_athlete_setup as intake

    try:
        if validate_latest:
            await intake.pin_context(repository, session, owner, proposal["athlete_context"])
        sources = {}
        for kind in ("profile", "availability"):
            ref = proposal["athlete_context"][kind + "_reference"]
            sources[kind] = None
            if ref:
                item, _record = await intake.load(repository, owner, kind, ref["artifact_id"])
                setup_domain.require(
                    setup_domain.reference(item) == ref, "ATHLETE_REFERENCE_DIFFERS"
                )
                setup_domain.require(
                    item["created_at"] <= created_at, "ATHLETE_CONTEXT_POSTDATES_PROGRAM"
                )
                if kind == "availability":
                    setup_domain.require(
                        item["timezone_name"] == timezone_name, "ATHLETE_CALENDAR_TIMEZONE_DIFFERS"
                    )
                sources[kind] = item
        setup_domain.require(sources["profile"] is not None, "ATHLETE_PROFILE_REQUIRED")
        first_macro = min(proposal["macrocycles"], key=lambda m: m["start_date"])
        first_meso = min(first_macro["mesocycles"], key=lambda m: m["start_date"])
        return setup_domain.planning_snapshot(
            sources["profile"],
            sources["availability"],
            created_at=created_at,
            timezone_name=timezone_name,
            start=first_meso["start_date"],
            end=first_meso["end_date"],
        )
    except setup_domain.SetupRuleError as exc:
        raise domain.CycleRuleError(exc.code) from None
    except (intake.SetupNotFound, intake.SetupStorageError) as exc:
        raise CycleStorageError("Owned athlete context unavailable.") from exc
