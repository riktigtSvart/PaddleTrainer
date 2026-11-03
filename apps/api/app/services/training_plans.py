"""Owner-serialized, append-only reviews and explicit atomic plan application."""

import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.entities import (
    AthleteReadiness,
    PlannedWorkout,
    User,
    WorkoutBlock,
    WorkoutSession,
    WorkoutStatus,
)
from app.planning.application import calendar_duration
from app.planning.application import create_cycle_program as programs
from app.planning.application import register_athlete_setup as transactions
from app.planning.domain.athlete_setup import digest, reference
from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind
from app.planning.domain.persistence.audit import AuditArtifactRecord
from app.planning.infrastructure.adapters.athlete_history import aware
from app.planning.infrastructure.persistence.sqlalchemy_models import (
    PlanningAuditArtifactRow,
    PlanningLogicalPlanRow,
)
from app.planning.infrastructure.repositories.postgres_planning_audit import (
    SqlAlchemyPlanningAuditRepository,
)
from app.schemas.workouts import WorkoutOut
from app.services import planning_inputs
from app.services import training_plan_policy as policy

SCHEMA = "training-plan-v0.1"
LIMIT = 2000
logger = logging.getLogger(__name__)


class TrainingPlanError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise TrainingPlanError(code)


def _now():
    return datetime.now(UTC)


def identity(owner, operation, token):
    return "pt-training-plan:" + digest({"owner": owner, "operation": operation, "token": token})


def decode(record, owner):
    value = json.loads(record.contract_json)
    require(
        record.athlete_id == owner
        and value["athlete_id"] == owner
        and value["artifact_id"] == record.artifact_id
        and value["schema_version"] == record.schema_version == SCHEMA
        and value["content_hash"]
        == record.content_hash
        == digest({k: v for k, v in value.items() if k != "content_hash"})
        and canonical_json(value) == record.contract_json
        and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
        and record.persisted_at is not None,
        "TRAINING_PLAN_STORAGE_INVALID",
    )
    return value


async def records(repo, session, owner, kind, program_id=None):
    rows = (
        (
            await session.execute(
                select(PlanningAuditArtifactRow.artifact_id)
                .where(
                    PlanningAuditArtifactRow.athlete_id == UUID(owner),
                    PlanningAuditArtifactRow.artifact_kind == kind.value,
                )
                .order_by(PlanningAuditArtifactRow.created_at, PlanningAuditArtifactRow.artifact_id)
                .limit(LIMIT + 1)
            )
        )
        .scalars()
        .all()
    )
    require(len(rows) <= LIMIT, "TRAINING_PLAN_HISTORY_LIMIT")
    values = []
    for row in rows:
        value = decode(await repo.get(artifact_kind=kind, artifact_id=row), owner)
        if program_id is None or value["program_id"] == program_id:
            values.append(value)
    return values


async def persist(repo, owner, kind, value):
    value = planning_inputs.wire(value)
    value.update(schema_version=SCHEMA, athlete_id=owner)
    value["content_hash"] = digest(value)
    require(len(canonical_json(value).encode()) < 8 * 1024 * 1024, "TRAINING_PLAN_SIZE_LIMIT")
    record = AuditArtifactRecord(
        artifact_kind=kind,
        artifact_id=value["artifact_id"],
        athlete_id=owner,
        schema_version=SCHEMA,
        created_at=policy.at(value["created_at"]),
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash=value["content_hash"],
        contract_json=canonical_json(value),
    )
    await repo.save(record)
    require(
        decode(await repo.get(artifact_kind=kind, artifact_id=value["artifact_id"]), owner)
        == value,
        "TRAINING_PLAN_STORAGE_INVALID",
    )
    return value


def snapshot(row):
    value = WorkoutOut.model_validate(row).model_dump(mode="json")
    if row.planned_start_time:
        value["planned_start_time"] = aware(row.planned_start_time).isoformat()
    value["blocks"] = sorted(
        [{k: v for k, v in b.items() if k != "id"} for b in value["blocks"]],
        key=lambda b: b["position"],
    )
    raw = {k: v for k, v in (row.raw_data or {}).items() if k != policy.MARKER}
    value = planning_inputs.wire(value)
    return value, digest({"workout": value, "raw_data": planning_inputs.wire(raw)})


async def assess(session, repo, owner, program_id, first, last, active_window_end=None, selection_preferences=None):
    user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
    low = _now().astimezone(ZoneInfo(user.timezone)).date() - timedelta(days=15)
    # These mutable records can also be corrected through older API paths.
    # Lock them before capture so the preview and the atomic writer see the
    # same values even when such an update does not take the owner lock.
    for model, column in (
        (WorkoutSession, WorkoutSession.started_at),
        (AthleteReadiness, AthleteReadiness.recorded_date),
        (PlannedWorkout, PlannedWorkout.date),
    ):
        boundary = (
            datetime.combine(low, datetime.min.time(), UTC) if model is WorkoutSession else low
        )
        locked = (
            (
                await session.execute(
                    select(model.id)
                    .where(model.user_id == UUID(owner), column >= boundary)
                    .limit(LIMIT + 1)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        require(len(locked) <= LIMIT, "TRAINING_PLAN_WORKOUT_LIMIT")
        if model is PlannedWorkout and locked:
            await session.execute(
                select(WorkoutBlock.id).where(WorkoutBlock.workout_id.in_(locked)).with_for_update()
            )
    data = await planning_inputs.capture(
        owner=owner,
        identity=program_id,
        session=session,
        first=first,
        last=last,
        close_transaction=False,
        max_days=366,
    )
    now = _now()
    today = now.astimezone(ZoneInfo(data["timezone_name"])).date()
    acceptances = await records(repo, session, owner, Kind.TRAINING_PLAN_ACCEPTANCE, program_id)
    known = {key: value for a in acceptances for key, value in a["created_workouts"].items()}
    rows = (
        (
            await session.execute(
                select(PlannedWorkout)
                .options(selectinload(PlannedWorkout.blocks))
                .where(
                    PlannedWorkout.user_id == UUID(owner),
                    PlannedWorkout.date.between(
                        today - timedelta(days=14),
                        datetime.fromisoformat(data["end_date"]).date() + timedelta(days=6),
                    ),
                )
                .order_by(PlannedWorkout.date, PlannedWorkout.id)
                .limit(LIMIT + 1)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    require(len(rows) <= LIMIT, "TRAINING_PLAN_WORKOUT_LIMIT")
    ids = [row.id for row in rows]
    # Lock block edits and late execution-link inserts as part of the same
    # transaction. The owner lock serializes the application revision writers.
    if ids:
        await session.execute(
            select(WorkoutBlock.id).where(WorkoutBlock.workout_id.in_(ids)).with_for_update()
        )
    links = (
        set(
            (
                await session.execute(
                    select(WorkoutSession.planned_workout_id)
                    .where(
                        WorkoutSession.user_id == UUID(owner),
                        WorkoutSession.planned_workout_id.in_(ids),
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        if ids
        else set()
    )
    adopted = (
        set(
            (
                await session.execute(
                    select(PlanningLogicalPlanRow.source_workout_id).where(
                        PlanningLogicalPlanRow.athlete_id == UUID(owner),
                        PlanningLogicalPlanRow.source_workout_id.in_(ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        if ids
        else set()
    )
    estimates = await calendar_duration.project(
        owner=owner, plans=rows, session=session, now=now, zone=data["timezone_name"]
    )
    plans = []
    for row in rows:
        w, hashed = snapshot(row)
        receipt = known.get(str(row.id))
        marker = (row.raw_data or {}).get(policy.MARKER)
        owned = bool(
            receipt
            and marker == receipt["marker"]
            and row.source == policy.SOURCE
            and row.polar_target_id is None
        )
        replaceable = bool(
            owned
            and hashed == receipt["workout_hash"]
            and row.status in {WorkoutStatus.PLANNED, WorkoutStatus.SCHEDULED, WorkoutStatus.DRAFT}
            and row.planned_start_time
            and aware(row.planned_start_time) > now
            and row.id not in links
            and row.id not in adopted
        )
        plans.append(
            {
                "workout": w,
                "workout_hash": hashed,
                "owned_sample": owned,
                "linked": row.id in links,
                "replaceable": replaceable,
                "template_key": receipt["template_key"] if receipt else None,
                "candidate_key": receipt["candidate_key"] if receipt else None,
                "duration_estimate": estimates.get(str(row.id)),
            }
        )
    result = policy.build(data, plans, now, active_window_end=active_window_end, selection_preferences=selection_preferences)
    if any(day["reason"] == "SELECTED_ALTERNATIVE_NO_LONGER_AVAILABLE" for day in result["days_without_proposal"]):
        result["blockers"].append("SELECTED_ALTERNATIVE_NO_LONGER_AVAILABLE")
        result["create"], result["cancel"] = [], []
        result["keep"] = [plan["workout"]["id"] for plan in plans if plan["replaceable"] and data["start_date"] <= plan["workout"]["date"] <= data["end_date"]]
    stable = {
        k: data[k]
        for k in (
            "athlete_id",
            "program_reference",
            "timezone_name",
            "start_date",
            "end_date",
            "periods",
            "competitions",
            "declared_goals",
            "program_sport",
            "goal_versions",
            "profile",
            "calendar_reference",
            "availability_reference",
            "boundary_reference",
            "competition_reference",
            "days",
            "recent_sessions",
            "recovery_records",
            "feedback",
            "gaps",
        )
    }
    key = digest(
        {"sources": {**stable, **({"training_options_reference": data["training_options_reference"]} if data.get("training_options_reference") else {})}, "plans": [
            {**p, "duration_estimate": {k: v for k, v in p["duration_estimate"].items() if k != "as_of"}
             if p["duration_estimate"] else None} for p in plans
        ], "result": result, "local_today": today.isoformat(), **({"selection_preferences": selection_preferences} if selection_preferences else {})}
    )
    return data, plans, result, key, now, {str(row.id): row for row in rows}


async def review(*, session, owner, program_id, first=None, last=None, active_window_end=None, selection_preferences=None, choice_request=None):
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        await transactions.lock_owner(session, owner)
        history = await records(repo, session, owner, Kind.TRAINING_PLAN_REVIEW, program_id)
        if choice_request:
            replay = next((item for item in history if item.get("choice_request") == choice_request), None)
            if replay:
                return {"review": replay, "reused": True}
            require(history and reference(history[-1]) == choice_request["review_reference"], "TRAINING_PLAN_REVIEW_CHANGED")
        if selection_preferences is None:
            selection_preferences = history[-1].get("selection_preferences", {}) if history else {}
        data, plans, result, key, now, _ = await assess(
            session, repo, owner, program_id, first, last, active_window_end=active_window_end, selection_preferences=selection_preferences
        )
        if history and history[-1]["decision_key"] == key:
            return {"review": history[-1], "reused": True}
        previous = reference(history[-1]) if history else None
        # Time is evidence only. It cannot cause a new revision on every poll.
        value = {
            "artifact_id": identity(
                owner, "review", {"program": program_id, "previous": previous, "key": key}
            ),
            "program_id": program_id,
            "created_at": now.isoformat(),
            "previous_reference": previous,
            "decision_key": key,
            "start_date": data["start_date"],
            "end_date": data["end_date"],
            "timezone_name": data["timezone_name"],
            "active_window_end": active_window_end,
            "program_reference": data["program_reference"],
            "inputs": data,
            "plan_snapshots": plans,
            "result": result,
            "committed_plan": False,
            "requires_explicit_acceptance": True,
            "selection_preferences": selection_preferences,
            **({"choice_request": choice_request} if choice_request else {}),
        }
        value = await persist(repo, owner, Kind.TRAINING_PLAN_REVIEW, value)
        await transactions.commit(session)
        return {"review": value, "reused": False}
    finally:
        await transactions.rollback(session)


async def choose(*, session, owner, program_id, proposal):
    """A choice recalculates a review; applying workouts remains a separate write."""
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        saved = await repo.get(artifact_kind=Kind.TRAINING_PLAN_REVIEW, artifact_id=proposal["review_reference"]["artifact_id"])
        require(saved is not None and saved.athlete_id == owner, "TRAINING_PLAN_REVIEW_CHANGED")
        viewed = decode(saved, owner)
        require(viewed["program_id"] == program_id and reference(viewed) == proposal["review_reference"], "TRAINING_PLAN_REVIEW_CHANGED")
        group = next((item for item in viewed["result"].get("alternatives", []) if item["date"] == proposal["date"]), None)
        candidate = next((item for item in group["candidates"] if item["candidate_key"] == proposal["candidate_key"]), None) if group else None
        require(candidate is not None, "TRAINING_PLAN_ALTERNATIVE_NOT_AVAILABLE")
        preferences = {**viewed.get("selection_preferences", {}), proposal["date"]: {"template_key": candidate["template_key"], "opportunity_key": candidate["opportunity_key"]}}
    finally:
        await transactions.rollback(session)
    return await review(session=session, owner=owner, program_id=program_id, first=viewed["start_date"], last=viewed["end_date"], active_window_end=viewed.get("active_window_end"), selection_preferences=preferences, choice_request=proposal)


async def status(*, session, owner, program_id):
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        await programs._load(repo, owner, programs.PROGRAM, program_id)
        reviews = await records(repo, session, owner, Kind.TRAINING_PLAN_REVIEW, program_id)
        acceptances = await records(repo, session, owner, Kind.TRAINING_PLAN_ACCEPTANCE, program_id)
        return {
            "review": reviews[-1] if reviews else None,
            "acceptance": acceptances[-1] if acceptances else None,
            "automatic_review_interval_seconds": 60,
        }
    finally:
        await transactions.rollback(session)


async def retry(repo, owner, operation, proposal, kind):
    key = identity(owner, operation, proposal["request_id"])
    saved = await repo.get(artifact_kind=kind, artifact_id=key)
    if saved:
        value = decode(saved, owner)
        require(value["proposal"] == proposal, "TRAINING_PLAN_REQUEST_CONFLICT")
        return {"artifact": value, "reused": True, "committed": True}
    return None


async def accept(*, session, owner, program_id, proposal):
    proposal = {**proposal, "program_id": program_id}
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        await transactions.lock_owner(session, owner)
        previous = await retry(repo, owner, "accept", proposal, Kind.TRAINING_PLAN_ACCEPTANCE)
        if previous:
            return previous
        saved = await repo.get(
            artifact_kind=Kind.TRAINING_PLAN_REVIEW,
            artifact_id=proposal["review_reference"]["artifact_id"],
        )
        require(saved is not None and saved.athlete_id == owner, "TRAINING_PLAN_REVIEW_CHANGED")
        viewed = decode(saved, owner)
        require(
            viewed["program_id"] == program_id
            and reference(viewed) == proposal["review_reference"],
            "TRAINING_PLAN_REVIEW_CHANGED",
        )
        history = await records(repo, session, owner, Kind.TRAINING_PLAN_REVIEW, program_id)
        require(reference(history[-1]) == reference(viewed), "TRAINING_PLAN_REVIEW_CHANGED")
        require(
            viewed["start_date"]
            >= _now().astimezone(ZoneInfo(viewed["timezone_name"])).date().isoformat(),
            "TRAINING_PLAN_REVIEW_CHANGED",
        )
        data, _plans, result, key, now, rows = await assess(
            session,
            repo,
            owner,
            program_id,
            viewed["start_date"],
            viewed["end_date"],
            active_window_end=viewed.get("active_window_end"),
            selection_preferences=viewed.get("selection_preferences", {}),
        )
        require(key == viewed["decision_key"], "TRAINING_PLAN_REVIEW_CHANGED")
        require(
            not result["blockers"] and (result["create"] or result["cancel"]),
            "TRAINING_PLAN_NO_CHANGES",
        )
        created = {}
        for candidate in result["create"]:
            require(policy.at(candidate["start_at"]) > now, "TRAINING_PLAN_REVIEW_CHANGED")
            plan_id = uuid5(
                NAMESPACE_URL,
                f"paddletrainer:{owner}:{viewed['artifact_id']}:{candidate['candidate_key']}",
            )
            marker = {
                "program_id": program_id,
                "review_id": viewed["artifact_id"],
                "candidate_key": candidate["candidate_key"],
            }
            row = PlannedWorkout(
                id=plan_id,
                user_id=UUID(owner),
                date=datetime.fromisoformat(candidate["date"]).date(),
                training_period_id=UUID(candidate["training_period_id"]),
                planned_start_time=policy.at(candidate["start_at"]),
                sport=candidate["sport"],
                title=candidate["title"],
                description=candidate["description"],
                duration_sec=candidate["duration_sec"],
                status=WorkoutStatus.PLANNED,
                source=policy.SOURCE,
                raw_data={policy.MARKER: marker},
                blocks=[WorkoutBlock(**b) for b in candidate["blocks"]],
            )
            session.add(row)
            await session.flush()
            _, hashed = snapshot(row)
            created[str(plan_id)] = {
                "workout_hash": hashed,
                "marker": marker,
                "candidate_key": candidate["candidate_key"],
                "template_key": candidate["template_key"],
            }
        for key in result["cancel"]:
            rows[key].status = WorkoutStatus.CANCELLED
            rows[key].updated_at = now
        await session.flush()
        artifact = await persist(
            repo,
            owner,
            Kind.TRAINING_PLAN_ACCEPTANCE,
            {
                "artifact_id": identity(owner, "accept", proposal["request_id"]),
                "program_id": program_id,
                "created_at": now.isoformat(),
                "proposal": proposal,
                "review_reference": reference(viewed),
                "start_date": data["start_date"],
                "end_date": data["end_date"],
                "created_workouts": created,
                "cancelled_workout_ids": result["cancel"],
                "kept_workout_ids": result["keep"],
                "authority_scope": "explicitly_reviewed_current_application_sample_plan",
                "personal_model_applied": False,
                "provider_writeback": False,
            },
        )
        await transactions.commit(session)
        return {"artifact": artifact, "reused": False, "committed": True}
    finally:
        await transactions.rollback(session)


async def confirm_missed(*, session, owner, program_id, proposal):
    proposal = {**proposal, "program_id": program_id}
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        await transactions.lock_owner(session, owner)
        saved = await retry(repo, owner, "missed", proposal, Kind.TRAINING_PLAN_OUTCOME)
        if saved:
            return saved
        user = await programs.timezone_for(session, owner)
        today = _now().astimezone(ZoneInfo(user)).date().isoformat()
        _, plans, _, _, now, rows = await assess(session, repo, owner, program_id, today, today)
        plan = next((p for p in plans if p["workout"]["id"] == proposal["workout_id"]), None)
        require(
            plan is not None
            and plan["owned_sample"]
            and not plan["linked"]
            and plan["workout_hash"] == proposal["expected_workout_hash"],
            "TRAINING_PLAN_OUTCOME_CHANGED",
        )
        w = plan["workout"]
        require(
            w["status"] in {"PLANNED", "DRAFT", "SCHEDULED"}
            and w["planned_start_time"]
            and w["duration_sec"] is not None
            and policy.at(w["planned_start_time"]) + timedelta(seconds=w["duration_sec"]) <= now,
            "TRAINING_PLAN_OUTCOME_NOT_ELAPSED",
        )
        rows[w["id"]].status = WorkoutStatus.SKIPPED
        rows[w["id"]].updated_at = now
        await session.flush()
        value = await persist(
            repo,
            owner,
            Kind.TRAINING_PLAN_OUTCOME,
            {
                "artifact_id": identity(owner, "missed", proposal["request_id"]),
                "program_id": program_id,
                "proposal": proposal,
                "created_at": now.isoformat(),
                "previous_workout": plan,
                "outcome": "athlete_confirmed_missed",
                "automatic_compensation": False,
            },
        )
        await transactions.commit(session)
        return {"artifact": value, "reused": False, "committed": True}
    finally:
        await transactions.rollback(session)


async def refresh_active(session, owner):
    """Catch up persisted events and elapsed windows, including after restart."""
    repo = SqlAlchemyPlanningAuditRepository(session)
    try:
        acceptances = await records(repo, session, owner, Kind.TRAINING_PLAN_ACCEPTANCE)
        programs_to_review = {a["program_id"]: a for a in acceptances}
        timezone_name = await programs.timezone_for(session, owner)
        today = _now().astimezone(ZoneInfo(timezone_name)).date().isoformat()
    finally:
        await transactions.rollback(session)
    results = []
    for program_id, accepted in programs_to_review.items():
        if (
            today
            > (datetime.fromisoformat(accepted["end_date"]).date() + timedelta(days=14)).isoformat()
        ):
            continue
        first = max(today, accepted["start_date"])
        last = max(first, accepted["end_date"])
        try:
            results.append(
                await review(
                    session=session,
                    owner=owner,
                    program_id=program_id,
                    first=first,
                    last=last,
                    active_window_end=accepted["end_date"],
                )
            )
        except Exception:
            logger.exception("Programme review failed; later programmes will still be checked")
            results.append({"program_id": program_id, "error": "retry_required"})
    return results
