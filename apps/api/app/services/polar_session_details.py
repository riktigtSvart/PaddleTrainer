"""Bounded, resumable acquisition of optional Polar statistics and samples."""
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
import math
from types import SimpleNamespace
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.integrations.polar.client import PolarClient
from app.models.entities import ExternalConnection, ProviderDataRecord, WorkoutSession
from app.planning.application import register_athlete_setup as transactions
from app.planning.domain.common.serialization import compute_content_hash
from app.planning.infrastructure.adapters.athlete_history import aware
from app.services.polar_tokens import get_valid_access_token
from app.services.polar_raw_preservation import PolarRawPreservationError, _assert_compatible, _id
from app.services.provider_payload_archive import archive_payload

LEGACY_FEATURES = ["statistics", "samples"]
ZONE_FEATURES = ["statistics", "samples", "zones"]
FEATURES = ["statistics", "samples", "zones", "laps"]
DAY_LIMIT = 5
ROW_LIMIT = 2000
RECEIPT_LIMIT = 10000
RECEIPT_TYPE = "DATA_SYNC_SESSION_DETAILS_FETCH"
EMPTY_RECHECK = timedelta(minutes=5)


def now():
    return datetime.now(UTC)


def require(condition, code):
    if not condition:
        raise PolarRawPreservationError(code)


def digest(value):
    return compute_content_hash(value, exclude_fields=frozenset())


def signature(row):
    raw = row.raw_data if isinstance(row.raw_data, dict) else {}
    return digest({"external_id": row.external_id, **{key: raw.get(key) for key in (
        "identifier", "modified", "startTime", "stopTime", "timezoneOffsetMinutes", "durationMillis",
        "distanceMeters", "sport", "hrAvg", "hrMax", "trainingTarget")}})


def source_day(row, zone):
    raw = row.raw_data if isinstance(row.raw_data, dict) else {}
    value = raw.get("startTime")
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    return aware(row.started_at).astimezone(ZoneInfo(zone)).date()


def additive(old, new):
    """Only fill absent data or add distinct typed channels; never erase a value."""
    if old is None or old == [] or old == {}:
        return deepcopy(new)
    if new is None or new == [] or new == {}:
        return deepcopy(old)
    if isinstance(old, dict) and isinstance(new, dict):
        result = deepcopy(old)
        for key, value in new.items():
            result[key] = additive(old[key], value) if key in old else deepcopy(value)
        return result
    if isinstance(old, list) and isinstance(new, list) and all(isinstance(x, dict) and isinstance(x.get("type"), str) for x in old + new):
        require(len({x["type"] for x in old}) == len(old) and len({x["type"] for x in new}) == len(new), "POLAR_DETAILS_DUPLICATE_CHANNEL")
        result = deepcopy(old)
        positions = {x["type"]: i for i, x in enumerate(old)}
        for item in new:
            if item["type"] in positions:
                index = positions[item["type"]]
                result[index] = additive(old[index], item)
            else:
                result.append(deepcopy(item))
        return result
    require(type(old) is not bool and type(new) is not bool and old == new or type(old) is type(new) and old == new,
            "POLAR_DETAILS_SOURCE_CONFLICT")
    return deepcopy(old)


def merge_details(stored, incoming, external_id):
    require(stored is None or isinstance(stored, dict), "POLAR_DETAILS_SOURCE_CONFLICT")
    old = stored or {}
    require(isinstance(incoming, dict) and _id(incoming) == external_id and _id(old) in (None, external_id),
            "POLAR_DETAILS_IDENTITY_CONFLICT")
    _assert_compatible(old, incoming)
    exercises = incoming.get("exercises")
    if exercises is None:
        exercises = []
    require(isinstance(exercises, list) and all(isinstance(e, dict) for e in exercises), "POLAR_DETAILS_EXERCISES_INVALID")
    ids = [_id(e) for e in exercises]
    require(None not in ids and len(set(ids)) == len(ids), "POLAR_DETAILS_EXERCISES_INVALID")
    previous = old.get("exerciseSamples")
    result = deepcopy(old)
    if not exercises:
        return result
    if previous:
        require(isinstance(previous, list) and all(isinstance(e, dict) for e in previous), "POLAR_DETAILS_SOURCE_CONFLICT")
        previous_ids = [_id(e) for e in previous]
        require(set(previous_ids) == set(ids) and len(set(previous_ids)) == len(previous_ids), "POLAR_DETAILS_EXERCISE_SET_CONFLICT")
        by_id = dict(zip(ids, exercises))
        result["exerciseSamples"] = [merge_exercise(e, by_id[_id(e)]) for e in previous]
    else:
        # A separate enrichment view preserves every base/native route field.
        result["exerciseSamples"] = deepcopy(exercises)
    native = old.get("exercises")
    if isinstance(native, list):
        by_id = dict(zip(ids, exercises))
        if any(isinstance(e, dict) and (e.get("samples") or e.get("routes") or e.get("zones") or e.get("laps")) for e in native):
            native_ids = [_id(e) for e in native if isinstance(e, dict)]
            require(len(native_ids) == len(native) and None not in native_ids and set(native_ids) == set(ids)
                    and len(set(native_ids)) == len(native_ids), "POLAR_DETAILS_EXERCISE_SET_CONFLICT")
        for exercise in native:
            if isinstance(exercise, dict) and exercise.get("laps"):
                require(_id(exercise) in by_id, "POLAR_DETAILS_EXERCISE_SET_CONFLICT")
                target = next(e for e in result["exerciseSamples"] if _id(e) == _id(exercise))
                target["laps"] = additive(exercise["laps"], target.get("laps"))
            if isinstance(exercise, dict) and exercise.get("zones"):
                require(_id(exercise) in by_id, "POLAR_DETAILS_EXERCISE_SET_CONFLICT")
                target = next(e for e in result["exerciseSamples"] if _id(e) == _id(exercise))
                target["zones"] = additive(exercise["zones"], target.get("zones"))
            if isinstance(exercise, dict) and exercise.get("samples"):
                require(_id(exercise) in by_id, "POLAR_DETAILS_EXERCISE_SET_CONFLICT")
                # Validate existing observations, while keeping their native view intact.
                left, right = exercise["samples"], by_id[_id(exercise)].get("samples")
                additive({"samples": left} if isinstance(left, list) else left,
                         {"samples": right} if isinstance(right, list) else right)
                # The preferred enrichment view must not hide older native
                # samples if the new response contains only statistics.
                target = next(e for e in result["exerciseSamples"] if _id(e) == _id(exercise))
                current = target.get("samples")
                target["samples"] = additive({"samples": left} if isinstance(left, list) else left,
                    {"samples": current} if isinstance(current, list) else current)
    return result


def merge_exercise(old, incoming):
    left, right = deepcopy(old), deepcopy(incoming)
    for item in (left, right):
        if isinstance(item.get("samples"), list):
            item["samples"] = {"samples": item["samples"]}
    return additive(left, right)


def has_samples(raw):
    for exercise in raw.get("exerciseSamples") or raw.get("exercises") or []:
        container = exercise.get("samples") if isinstance(exercise, dict) else None
        channels = container if isinstance(container, list) else container.get("samples") if isinstance(container, dict) else []
        if isinstance(channels, list) and any(isinstance(c, dict) and isinstance(c.get("values"), list) and len(c["values"]) > 0 for c in channels):
            return True
    return False


def update_statistics(row, incoming):
    exercises = incoming.get("exercises") or []
    if len(exercises) != 1:
        return  # Do not average different sports or mislabel the first part as the whole session.
    container = exercises[0].get("statistics")
    statistics = container.get("statistics") if isinstance(container, dict) else None
    if not isinstance(statistics, list):
        return
    names = {"STATISTICS_TYPE_HEART_RATE": ("avg_hr", "max_hr"), "STATISTICS_TYPE_SPEED": ("avg_speed", "max_speed"),
             "STATISTICS_TYPE_CADENCE": ("avg_cadence", "max_cadence"), "STATISTICS_TYPE_POWER": ("avg_power", "max_power")}
    for item in statistics:
        if not isinstance(item, dict) or item.get("type") not in names:
            continue
        for key, column in zip(("avg", "max"), names[item["type"]]):
            value = item.get(key)
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                setattr(row, column, value)


async def synchronize_details(db, user, *, first, last, report):
    owner, zone = str(user.id), user.timezone
    user_stub = SimpleNamespace(id=UUID(owner))
    report.update(imported=0, updated=0, skipped=0, skip_reasons={})
    rows = list((await db.execute(select(WorkoutSession).where(
        WorkoutSession.user_id == UUID(owner), WorkoutSession.external_provider == "POLAR",
        WorkoutSession.started_at >= datetime.combine(first, datetime.min.time(), UTC) - timedelta(hours=14),
        WorkoutSession.started_at < datetime.combine(last, datetime.min.time(), UTC) + timedelta(hours=14)
    ).limit(ROW_LIMIT + 1))).scalars())
    require(len(rows) <= ROW_LIMIT, "POLAR_DETAILS_WINDOW_TOO_DENSE")
    requested = {str(r.id): {"id": r.id, "external_id": r.external_id, "signature": signature(r), "day": source_day(r, zone)}
                 for r in rows if first <= source_day(r, zone) < last}
    receipts = list((await db.execute(select(ProviderDataRecord).where(
        ProviderDataRecord.user_id == UUID(owner), ProviderDataRecord.provider == "POLAR", ProviderDataRecord.data_type == RECEIPT_TYPE,
        ProviderDataRecord.period_start >= datetime.combine(first, datetime.min.time(), UTC),
        ProviderDataRecord.period_start < datetime.combine(last, datetime.min.time(), UTC)
    ).limit(RECEIPT_LIMIT + 1))).scalars())
    require(len(receipts) <= RECEIPT_LIMIT, "POLAR_DETAILS_RECEIPT_WINDOW_TOO_DENSE")
    checked = now()
    complete = set()
    for record in receipts:
        value = record.raw_data
        require(isinstance(value, dict) and record.provider_record_id == "sync:" + digest(value) and value.get("athlete_id") == owner
                and value.get("schema_version") == "polar-session-details-fetch-v0.1"
                and value.get("features") in (LEGACY_FEATURES, ZONE_FEATURES, FEATURES),
                "POLAR_DETAILS_RECEIPT_INVALID")
        candidate = requested.get(value.get("session_id"))
        if candidate and value.get("source_signature") == candidate["signature"]:
            require(type(value.get("with_samples")) is bool, "POLAR_DETAILS_RECEIPT_INVALID")
            if value["features"] == FEATURES and (value["with_samples"] or aware(record.fetched_at) >= checked - EMPTY_RECHECK):
                complete.add(value["session_id"])
    connection = (await db.execute(select(ExternalConnection).where(ExternalConnection.user_id == UUID(owner), ExternalConnection.provider == "POLAR"))).scalar_one_or_none()
    require(connection is not None, "POLAR_DETAILS_CONNECTION_MISSING")
    token = await get_valid_access_token(db, connection)
    await db.rollback()  # Release these local reads before fetching the per-day detail payloads.
    pending = {k: v for k, v in requested.items() if k not in complete}
    days = sorted({r["day"] for r in pending.values()}, reverse=True)
    fetched, with_samples, attempts, reasons = set(), set(), 0, {}

    def progress():
        left = set(pending) - fetched
        remainder = dict(reasons)
        unassigned = len(left) - sum(remainder.values())
        if unassigned:
            remainder["details_batch_pending"] = unassigned
        report.update(updated=len(fetched), skipped=len(left), skip_reasons=remainder,
            details={"requested_sessions": len(requested), "already_complete": len(complete), "fetched_sessions": len(fetched),
                     "with_samples": len(with_samples), "without_samples": len(fetched) - len(with_samples),
                     "pending_sessions": len(left), "processed_days": attempts,
                     "pending_days": len({pending[k]["day"] for k in left})})

    progress()
    try:
        for day in days[:DAY_LIMIT]:
            payload = await PolarClient().list_training_sessions(token, day, day + timedelta(days=1), features=FEATURES)
            items = payload.get("trainingSessions") if isinstance(payload, dict) else None
            require(isinstance(items, list) and all(isinstance(i, dict) and _id(i) for i in items)
                    and len({_id(i) for i in items}) == len(items), "POLAR_DETAILS_PAYLOAD_INVALID")
            by_id = {_id(item): item for item in items}
            await transactions.lock_owner(db, owner)
            await archive_payload(db, user_stub, "DATA_SYNC_SESSION_DETAILS", payload, first=day, last=day + timedelta(days=1))
            saved, sampled = set(), set()
            for identity, candidate in pending.items():
                if candidate["day"] != day:
                    continue
                incoming = by_id.get(candidate["external_id"])
                if incoming is None:
                    reasons["details_not_returned"] = reasons.get("details_not_returned", 0) + 1
                    continue
                row = (await db.execute(select(WorkoutSession).where(WorkoutSession.id == candidate["id"], WorkoutSession.user_id == UUID(owner))
                                        .with_for_update())).scalar_one_or_none()
                if row is None or signature(row) != candidate["signature"]:
                    reasons["details_source_changed"] = reasons.get("details_source_changed", 0) + 1
                    continue
                try:
                    merged = merge_details(row.raw_data, incoming, row.external_id)
                except PolarRawPreservationError:
                    reasons["details_source_conflict"] = reasons.get("details_source_conflict", 0) + 1
                    continue
                if row.raw_data != merged:
                    await archive_payload(db, user_stub, "DATA_SYNC_PREVIOUS_SESSION", {"session_id": identity, "raw_data": row.raw_data})
                row.raw_data = merged
                update_statistics(row, incoming)
                available = has_samples({"exerciseSamples": incoming.get("exercises") or []})
                await archive_payload(db, user_stub, RECEIPT_TYPE, {
                    "schema_version": "polar-session-details-fetch-v0.1", "athlete_id": owner,
                    "session_id": identity, "source_signature": candidate["signature"], "with_samples": available,
                    "checked_at": now().isoformat(), "features": FEATURES,
                }, first=day, last=day + timedelta(days=1))
                saved.add(identity)
                if available:
                    sampled.add(identity)
            await db.commit()
            fetched.update(saved)
            with_samples.update(sampled)
            attempts += 1
            progress()
    finally:
        progress()
    if report["skipped"]:
        report["error_code"] = "DATA_SYNC_DETAILS_SOURCE_CONFLICT" if any(k in reasons for k in ("details_source_changed", "details_source_conflict")) else \
            "DATA_SYNC_DETAILS_NOT_RETURNED" if "details_not_returned" in reasons else "DATA_SYNC_DETAILS_PENDING"
