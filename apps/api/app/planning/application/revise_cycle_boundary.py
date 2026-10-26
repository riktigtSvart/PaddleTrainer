"""Atomic period-date update and immutable evidence, with exact safe retry."""

from datetime import date
from uuid import UUID

from sqlalchemy import select

from app.models.entities import PlannedWorkout, TrainingPeriod
from app.planning.domain import cycle_boundary as boundary
from app.planning.domain.cycle_program import CycleRuleError, reference
from app.planning.domain.persistence.audit import AuditArtifactKind

from . import create_cycle_program as programs

KIND = AuditArtifactKind.CYCLE_MESOCYCLE_BOUNDARY_REVISION


async def lock_periods(session, owner, program):
    result = await session.execute(
        select(TrainingPeriod)
        .where(
            TrainingPeriod.user_id == UUID(owner),
            TrainingPeriod.id.in_([UUID(p["id"]) for p in program["periods"]]),
        )
        .order_by(TrainingPeriod.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return {str(p.id): p for p in result.scalars().all()}


async def head(repository, owner, program, *, kind=KIND):
    values, cache = [], {}
    for number in range(1, 65):
        identity = (
            boundary.slot(owner, program["proposal"]["program_id"], number)
            if kind == KIND
            else programs.domain.slot(owner, program["proposal"]["program_id"], revision=number)
        )
        row = await repository.get(artifact_kind=kind, artifact_id=identity)
        if row is None:
            break
        artifact, record = await programs._load(repository, owner, kind, identity, cache=cache)
        values.append(programs.receipt(artifact, record, reused=True))
    return values


def verify_rows(rows, expected, owner, identity):
    if len(rows) != len(expected):
        raise CycleRuleError("CYCLE_BOUNDARY_SOURCE_CHANGED")
    for p in expected:
        row = rows.get(p["id"])
        if (
            row is None
            or str(row.user_id) != owner
            or (str(row.parent_id) if row.parent_id else None) != p["parent_id"]
            or row.period_type.value != p["period_type"]
            or row.title != p["title"]
            or row.start_date.isoformat() != p["start_date"]
            or row.end_date.isoformat() != p["end_date"]
            or row.extra_data.get("cycle_program_artifact_id") != identity
        ):
            raise CycleRuleError("CYCLE_BOUNDARY_SOURCE_CHANGED")


async def revise(*, owner, proposal, repository, session):
    programs.transactions._require_session(repository, session)
    try:
        program, _ = await programs._load(
            repository, owner, programs.PROGRAM, proposal["program_reference"]["artifact_id"]
        )
        programs._same_reference(program, proposal["program_reference"])
        identity = boundary.slot(owner, program["proposal"]["program_id"], proposal["revision"])
        existing = await repository.get(artifact_kind=KIND, artifact_id=identity)
        if existing is not None:
            artifact, record = await programs._load(repository, owner, KIND, identity)
            if artifact["proposal"] != proposal:
                raise CycleRuleError("CYCLE_REQUEST_IDENTITY_CONFLICT")
            await programs.transactions._rollback(session)
            return programs.receipt(artifact, record, reused=True)
        rows = await lock_periods(session, owner, program)
        changes = await head(repository, owner, program)
        previous = changes[-1]["artifact"] if changes else None
        if proposal["revision"] != len(changes) + 1 or proposal["previous_reference"] != (
            reference(previous) if previous else None
        ):
            raise CycleRuleError("CYCLE_REVISION_CHAIN")
        events = await head(repository, owner, program, kind=programs.EVENTS)
        competition = events[-1]["artifact"] if events else program
        expected = previous["periods"] if previous else program["periods"]
        verify_rows(rows, expected, owner, program["artifact_id"])
        artifact = boundary.build(
            proposal,
            program=program,
            previous=previous,
            competition=competition,
            created_at=programs._now().isoformat(),
            timezone_name=await programs.timezone_for(session, owner),
        )
        updated = {p["id"]: p for p in artifact["periods"]}
        pair = [proposal["left_period_id"], proposal["right_period_id"]]
        # Dates never move an existing workout or a nested microcycle out of its assigned period.
        workouts = await session.execute(
            select(PlannedWorkout).where(
                PlannedWorkout.user_id == UUID(owner),
                PlannedWorkout.training_period_id.in_([UUID(p) for p in pair]),
            )
        )
        for workout in workouts.scalars().all():
            p = updated[str(workout.training_period_id)]
            if not p["start_date"] <= workout.date.isoformat() <= p["end_date"]:
                raise CycleRuleError("CYCLE_BOUNDARY_WORKOUT_REPLAN_REQUIRED")
        children = await session.execute(
            select(TrainingPeriod).where(
                TrainingPeriod.user_id == UUID(owner),
                TrainingPeriod.parent_id.in_([UUID(p) for p in pair]),
            )
        )
        for child in children.scalars().all():
            p = updated[str(child.parent_id)]
            if (
                not p["start_date"]
                <= child.start_date.isoformat()
                <= child.end_date.isoformat()
                <= p["end_date"]
            ):
                raise CycleRuleError("CYCLE_BOUNDARY_CHILD_REPLAN_REQUIRED")
        for identity_ in pair:
            p = updated[identity_]
            rows[identity_].start_date = date.fromisoformat(p["start_date"])
            rows[identity_].end_date = date.fromisoformat(p["end_date"])
            rows[identity_].extra_data = {
                **rows[identity_].extra_data,
                "cycle_dates_role": "provisional",
                "cycle_boundary_revision_id": artifact["artifact_id"],
            }
        await session.flush()
        stored_rows = await lock_periods(session, owner, program)
        verify_rows(stored_rows, artifact["periods"], owner, program["artifact_id"])
        record = await programs._save(repository, artifact, KIND)
        await programs._commit(session)
        return programs.receipt(artifact, record, reused=False)
    except BaseException:
        await programs.transactions._rollback(session)
        raise
