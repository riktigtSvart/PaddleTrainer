"""Read-only execution reconciliation from stored sessions and durable sync receipts.

Absence means no recorded completion after a covered import. It is a reversible
planning assessment, never a fabricated observation or a mutation of a plan.
"""

from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models.entities import PlannedWorkout, WorkoutSession
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind
from app.planning.infrastructure.adapters.athlete_history import aware
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.services import data_connections

SCHEMA = "training-execution-reconciliation-v0.1"
LIMIT = 2000


def empty(owner):
    return {"schema_version": SCHEMA, "athlete_id": owner,
            "sync_windows": [], "resolved_links": [], "ambiguous_workout_ids": []}


def planned_span(workout, zone):
    """Without a known clock, wait until the entire declared civil day has ended."""
    if workout["planned_start_time"] and workout["duration_sec"] is not None:
        start = datetime.fromisoformat(workout["planned_start_time"])
        return start, start + timedelta(seconds=workout["duration_sec"])
    day = datetime.fromisoformat(workout["date"]).date()
    return (datetime.combine(day, time.min, ZoneInfo(zone)),
            datetime.combine(day + timedelta(days=1), time.min, ZoneInfo(zone)))


def absence_source(workout, zone, context):
    first, last = planned_span(workout, zone)
    if workout["id"] in context["ambiguous_workout_ids"]:
        return None
    return next((source for source in context["sync_windows"]
                 if datetime.fromisoformat(source["started_at"]) >= last
                 and datetime.fromisoformat(source["from_at"]) <= first
                 and last <= datetime.fromisoformat(source["to_exclusive_at"])), None)


def clean_sessions_report(end):
    reports = [item for item in end["datasets"] if item["dataset"] == "sessions"]
    if len(reports) != 1:
        return None
    report = reports[0]
    if (report["state"] != "succeeded" or report["error_code"] is not None
            or report["skipped"] != 0
            or any(type(report[key]) is not int or report[key] < 0
                   for key in ("imported", "updated", "skipped"))):
        return None
    return {key: report[key] for key in ("imported", "updated", "skipped")}


def provider_target(raw):
    target = raw.get("id") if isinstance(raw, dict) else None
    if (type(target) is int and target > 0
            or type(target) is str and 0 < len(target) <= 128 and target == target.strip()):
        return str(target)
    return None


async def capture(*, session, repository, owner, plans, sessions, cutoff, zone, history_span=None):
    result = empty(owner)
    wanted = {str(plan.id) for plan in plans}
    session_ids = [UUID(item["id"]) for item in sessions]
    metadata = (await session.execute(select(
        WorkoutSession.id,
        WorkoutSession.planned_workout_id,
        WorkoutSession.raw_data["trainingTarget"].label("target"),
    ).where(WorkoutSession.user_id == UUID(owner), WorkoutSession.id.in_(session_ids),
            WorkoutSession.external_provider == "POLAR"))).all() if session_ids else []
    references = {str(item.id): provider_target(item.target) for item in metadata}
    existing_links = {str(item.id): str(item.planned_workout_id) if item.planned_workout_id else None
                      for item in metadata}
    targets = {value for value in references.values() if value is not None}
    candidates = (await session.execute(select(
        PlannedWorkout.id, PlannedWorkout.polar_target_id,
    ).where(PlannedWorkout.user_id == UUID(owner), PlannedWorkout.polar_target_id.in_(targets))
      .order_by(PlannedWorkout.id).limit(LIMIT + 1))).all() if targets else []
    if len(candidates) > LIMIT:
        raise ValueError("TRAINING_EXECUTION_LINK_LIMIT")
    by_target = {}
    for plan in candidates:
        by_target.setdefault(plan.polar_target_id, []).append(str(plan.id))
    ambiguous = set()
    for session_id, target in sorted(references.items()):
        matched = by_target.get(target, [])
        existing = existing_links[session_id]
        if existing:
            if matched and (len(matched) != 1 or existing != matched[0]):
                ambiguous.update(set(matched) & wanted)
            continue
        if len(matched) > 1:
            ambiguous.update(set(matched) & wanted)
        elif len(matched) == 1 and matched[0] in wanted:
            result["resolved_links"].append({"session_id": session_id, "workout_id": matched[0],
                                             "basis": "provider_exact", "provider": "POLAR"})
    result["ambiguous_workout_ids"] = sorted(ambiguous)
    elapsed = []
    for plan in plans:
        if plan.status.value in {"COMPLETED", "SKIPPED", "CANCELLED"}:
            continue
        start, end = planned_span({"date": plan.date.isoformat(),
                                  "planned_start_time": aware(plan.planned_start_time).isoformat()
                                  if plan.planned_start_time else None,
                                  "duration_sec": plan.duration_sec}, zone)
        if end <= cutoff:
            elapsed.append((start, end))
    if not elapsed and history_span is None:
        return result
    # An import started before the plan ended cannot establish its absence.
    first_end = min([end for _, end in elapsed] + ([history_span[0]] if history_span else []))
    rows = (await session.execute(select(
        PlanningAuditArtifactRow.artifact_id, PlanningAuditArtifactRow.artifact_kind,
    ).where(
        PlanningAuditArtifactRow.athlete_id == UUID(owner),
        PlanningAuditArtifactRow.artifact_kind.in_([kind.value for kind in data_connections.TERMINAL]),
        PlanningAuditArtifactRow.created_at >= first_end,
        PlanningAuditArtifactRow.created_at <= cutoff,
        PlanningAuditArtifactRow.persisted_at <= cutoff,
    ).order_by(PlanningAuditArtifactRow.created_at.desc(), PlanningAuditArtifactRow.artifact_id.desc())
      .limit(LIMIT + 1))).all()
    if len(rows) > LIMIT:
        raise ValueError("TRAINING_EXECUTION_SYNC_HISTORY_LIMIT")
    for row in rows:
        end_record = await repository.get(artifact_kind=Kind(row.artifact_kind), artifact_id=row.artifact_id)
        end = data_connections.decode(end_record, owner)
        report = clean_sessions_report(end)
        if report is None or end["proposal"]["provider"] != "POLAR":
            continue
        start_record = await repository.get(artifact_kind=Kind.DATA_SYNC_STARTED, artifact_id=row.artifact_id)
        if start_record is None or start_record.persisted_at > cutoff:
            raise ValueError("TRAINING_EXECUTION_SYNC_SOURCE_INVALID")
        start = data_connections.decode(start_record, owner)
        if (end["start_reference"] != data_connections.reference(start)
                or end["proposal"] != start["proposal"]
                or datetime.fromisoformat(end["created_at"]) < datetime.fromisoformat(start["created_at"])):
            raise ValueError("TRAINING_EXECUTION_SYNC_SOURCE_INVALID")
        window = start["window"]
        timezone = ZoneInfo(window["timezone_name"])
        first = datetime.combine(datetime.fromisoformat(window["from_date"]).date(), time.min, timezone)
        last = datetime.combine(datetime.fromisoformat(window["sessions_to_exclusive"]).date(), time.min, timezone)
        if first >= last:
            raise ValueError("TRAINING_EXECUTION_SYNC_WINDOW_INVALID")
        if not (any(first <= a and b <= last and b <= datetime.fromisoformat(start["created_at"])
                    for a, b in elapsed)
                or history_span and first < history_span[1] and history_span[0] < last):
            continue
        result["sync_windows"].append({
            "start_reference": data_connections.reference(start),
            "result_reference": data_connections.reference(end),
            "provider": "POLAR", "started_at": start["created_at"], "finished_at": end["created_at"],
            "from_at": first.astimezone(UTC).isoformat(),
            "to_exclusive_at": last.astimezone(UTC).isoformat(),
            "timezone_name": window["timezone_name"], "sessions": report,
        })
    return result


def stable_result(result):
    """Repeating a successful import alone must not manufacture a new decision."""
    stable = {**{key: value for key, value in result.items() if key != "execution_reconciliation"},
              "events": [{key: value for key, value in event.items()
                          if key not in {"sync_reference", "checked_through"}}
                         for event in result["events"]]}
    context = result.get("prescription_context")
    if context:
        budget = context["starting_budget"]
        stable["prescription_context"] = {**{key: value for key, value in context.items() if key != "calibration_reference"}, "starting_budget": {
            **budget, "weeks": [{key: value for key, value in week.items() if key != "source_reference"}
                                 for week in budget["weeks"]]}}
    return stable
