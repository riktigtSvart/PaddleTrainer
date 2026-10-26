"""Read-only historical candidates. Source snapshots remain separate from manual corrections."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models.entities import (
    Assessment,
    AthleteReadiness,
    Measurement,
    PhysiologicalMeasurement,
    ProviderDataRecord,
    WorkoutSession,
)
from app.planning.domain.athlete_setup import UNITS, digest, require

# These are explicit aliases only; an unrecognised measure is never guessed to be VO2max.
METRICS = {key: key for key in UNITS}
METRICS.update(
    {
        "body_weight_kg": "body_mass_kg",
        "vo2max": "vo2max_ml_kg_min",
        "sleep_duration_seconds": "sleep_duration_sec",
        "background_hr_mean": "background_hr_mean_bpm",
    }
)
SOURCE_DOC = "https://www.polar.com/polar-api-v4/"
NORMALIZER = "athlete-history-candidates-v0.1"


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def number(value, divisor=1):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value)) / Decimal(divisor)
        if not result.is_finite() or result < 0:
            return None
        # Preserve the original provider bytes separately; display precision is explicit.
        text = format(result.quantize(Decimal("0.000001")), "f").rstrip("0").rstrip(".")
        return text or "0"
    except (InvalidOperation, TypeError, ValueError):
        return None


def candidate(
    *,
    metric,
    value,
    day,
    provider,
    source_id,
    source_hash,
    received_at,
    method,
    logical_key,
    sport="",
    protocol="",
    coverage=None,
):
    if metric not in UNITS or value is None:
        return None
    result = {
        "normalizer_version": NORMALIZER,
        "aggregation": "mean"
        if metric == "background_hr_mean_bpm"
        else "median"
        if metric == "background_hr_median_bpm"
        else "total"
        if metric == "daily_steps"
        else "single",
        "metric": metric,
        "value": value,
        "unit": UNITS[metric],
        "start_date": day,
        "end_date": day,
        "provider": provider,
        "source_id": source_id,
        "source_content_hash": source_hash,
        "received_at": received_at,
        "method": method,
        "logical_key": logical_key,
        "sport": sport,
        "protocol": protocol,
        "coverage": coverage or {"completeness": "unknown"},
    }
    result["artifact_id"] = "pt-source:" + digest(result)
    result["content_hash"] = digest(result)
    return result


def polar_values(domain, payload, requested_day):
    """Yield declared provider observations; retain unmapped fields in the raw record."""
    if domain == "sessions":
        for item in payload.get("trainingSessions", []):
            day = str(item.get("startTime", ""))[:10]
            external = (item.get("identifier") or {}).get("id")
            if day != requested_day or not external:
                continue
            sport = str((item.get("sport") or {}).get("id", ""))
            base = {
                "day": day,
                "sport": sport,
                "logical": f"sessions:{external}",
                "method": "recorded_activity",
            }
            yield {**base, "metric": "training_sessions", "value": "1"}
            duration = number(item.get("durationMillis"), 60000)
            if duration is not None:
                yield {**base, "metric": "training_minutes", "value": duration}
    elif domain == "sleep":
        for item in payload.get("nightSleeps", []):
            day = item.get("sleepDate")
            if day != requested_day:
                continue
            base = {"day": day, "logical": f"sleep:{day}", "method": "device_estimate"}
            duration = (item.get("sleepEvaluation") or {}).get("asleepDuration")
            if isinstance(duration, str) and duration.endswith("s"):
                duration = number(duration[:-1])
            else:
                duration = None
            if duration is not None:
                yield {**base, "metric": "sleep_duration_sec", "value": duration}
            score = number((item.get("sleepScore") or {}).get("sleepScore"))
            if score is not None:
                yield {**base, "metric": "sleep_score", "value": score}
    elif domain == "nightly_recharge":
        for item in payload.get("nightlyRechargeResults", []):
            if item.get("sleepResultDate") != requested_day:
                continue
            ans = item.get("ansStatus") or item.get("ansCharge") or item
            value = number(ans.get("meanNightlyRecoveryRmssd"))
            if value is None:
                value = number(item.get("meanNightlyRecoveryRmssd"))
            if value is not None:
                yield {
                    "day": requested_day,
                    "logical": f"nightly:{requested_day}",
                    "method": "device_measurement",
                    "metric": "hrv_rmssd_ms",
                    "value": value,
                }
    elif domain == "continuous_hr":
        body = payload.get("continuousSamples", payload)
        for item in body.get("heartRateSamplesPerDay", []):
            if item.get("date") != requested_day:
                continue
            samples = [
                s
                for s in item.get("samples", [])
                if s.get("triggerType") == "TRIGGER_TIMED_247"
                and type(s.get("heartRate")) is int
                and s["heartRate"] > 0
                and type(s.get("offsetMillis")) is int
            ]
            if not samples:
                continue
            device = str((item.get("deviceRef") or {}).get("deviceId", "unknown"))
            yield {
                "day": requested_day,
                "logical": f"continuous_hr:{requested_day}:{device}",
                "method": "device_measurement",
                "metric": "background_hr_mean_bpm",
                "value": number(sum(s["heartRate"] for s in samples), len(samples)),
                "coverage": {
                    "completeness": "sampled",
                    "sample_count": len(samples),
                    "first_offset_ms": min(s["offsetMillis"] for s in samples),
                    "last_offset_ms": max(s["offsetMillis"] for s in samples),
                    "is_resting_hr": False,
                },
            }
    elif domain == "activity":
        for item in (payload.get("activities") or {}).get("activityDays", []):
            if item.get("date") != requested_day:
                continue
            for index, device in enumerate(item.get("activitiesPerDevice", [])):
                identifier = str(
                    (device.get("deviceReference") or {}).get("deviceId", f"unknown-{index}")
                )
                buckets, invalid = {}, False
                for block in device.get("activitySamples", []):
                    vector = block.get("stepSamples")
                    if not vector:
                        continue
                    try:
                        start = time.fromisoformat(vector["startTime"])
                        interval = int(vector["interval"])
                        assert interval > 0 and start.tzinfo is None
                        offset = ((start.hour * 60 + start.minute) * 60 + start.second) * 1000
                        for i, value in enumerate(vector.get("steps", [])):
                            key = offset + i * interval
                            assert type(value) is int and value >= 0 and key + interval <= 86400000
                            assert not any(
                                key < stop and begin < key + interval for begin, stop in buckets
                            )
                            buckets[(key, key + interval)] = value
                    except (ValueError, KeyError, TypeError, AssertionError):
                        invalid = True
                if buckets and not invalid:
                    yield {
                        "day": requested_day,
                        "logical": f"activity:{requested_day}:{identifier}",
                        "method": "device_estimate",
                        "metric": "daily_steps",
                        "value": str(sum(buckets.values())),
                        "coverage": {
                            "completeness": "sampled",
                            "observed_minutes": number(
                                sum(end - start for start, end in buckets), 60000
                            ),
                            "device_id": identifier,
                            "devices_must_not_be_summed": True,
                        },
                    }
    elif domain == "tests":
        for item in (payload.get("data") or {}).get("tests", []):
            day = str(item.get("startTime", ""))[:10]
            result = item.get("fitnessTestResult") or {}
            value = number(result.get("ownIndex"))
            if day == requested_day and value is not None and Decimal(value) > 0:
                yield {
                    "day": day,
                    "logical": f"fitness_test:{item.get('startTime')}",
                    "method": "device_estimate",
                    "metric": "vo2max_ml_kg_min",
                    "value": value,
                    "protocol": "Polar Fitness Test / OwnIndex (becslés, nem laboratóriumi VO2max)",
                }


async def historical_candidates(session, owner, *, first, last, timezone_name):
    require(
        first <= last and (date.fromisoformat(last) - date.fromisoformat(first)).days < 366,
        "ATHLETE_HISTORY_RANGE_INVALID",
    )
    tz = ZoneInfo(timezone_name)
    start = datetime.combine(date.fromisoformat(first), time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(
        date.fromisoformat(last) + timedelta(days=1), time.min, tzinfo=tz
    ).astimezone(UTC)
    result = []

    def add(**kwargs):
        value = candidate(**kwargs)
        if value and first <= value["start_date"] <= last:
            result.append(value)
            require(len(result) <= 1000, "ATHLETE_HISTORY_TOO_LARGE_CHOOSE_SHORTER_RANGE")

    async def rows(statement):
        values = (await session.execute(statement.limit(2001))).scalars().all()
        require(len(values) <= 2000, "ATHLETE_HISTORY_TOO_LARGE_CHOOSE_SHORTER_RANGE")
        return values

    for row in await rows(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == UUID(owner),
            WorkoutSession.started_at >= start,
            WorkoutSession.started_at < end,
        )
        .order_by(WorkoutSession.started_at, WorkoutSession.id)
    ):
        day = aware(row.started_at).astimezone(tz).date().isoformat()
        base = {
            "day": day,
            "provider": row.external_provider,
            "source_id": "session:" + str(row.id),
            "source_hash": digest(
                {
                    "raw": row.raw_data,
                    "duration": row.duration_sec,
                    "start_time": aware(row.started_at).isoformat(),
                    "sport": str(row.sport),
                }
            ),
            "received_at": aware(row.created_at).isoformat(),
            "method": "recorded_activity",
            "sport": row.sport.value,
        }
        logical = f"{row.external_provider}:sessions:{row.external_id or row.id}"
        add(
            **base,
            metric="training_sessions",
            value="1",
            logical_key=logical + ":training_sessions",
        )
        add(
            **base,
            metric="training_minutes",
            value=number(row.duration_sec, 60),
            logical_key=logical + ":training_minutes",
        )
    for row in await rows(
        select(PhysiologicalMeasurement)
        .where(
            PhysiologicalMeasurement.user_id == UUID(owner),
            PhysiologicalMeasurement.measured_at >= start,
            PhysiologicalMeasurement.measured_at < end,
        )
        .order_by(PhysiologicalMeasurement.measured_at, PhysiologicalMeasurement.id)
    ):
        metric = METRICS.get(row.metric_key)
        if not metric or row.unit != UNITS[metric]:
            continue
        day = aware(row.measured_at).astimezone(tz).date().isoformat()
        snapshot = {
            "metric": row.metric_key,
            "value": row.value_float,
            "text": row.value_text,
            "unit": row.unit,
            "measured_at": aware(row.measured_at).isoformat(),
            "extra": row.extra_data,
            "source_record_id": row.source_record_id,
        }
        add(
            metric=metric,
            value=number(row.value_float),
            day=day,
            provider=row.provider,
            source_id="physiology:" + str(row.id),
            source_hash=digest(snapshot),
            received_at=aware(row.created_at).isoformat(),
            method="device_estimate"
            if metric in {"sleep_duration_sec", "sleep_score", "daily_steps", "vo2max_ml_kg_min"}
            else "device_measurement",
            logical_key=f"{row.provider}:physiology:{day}:{metric}:{row.device_id or ''}",
            coverage={"completeness": "unknown", "quality": row.quality},
        )
    readiness = await rows(
        select(AthleteReadiness)
        .where(
            AthleteReadiness.user_id == UUID(owner),
            AthleteReadiness.recorded_date >= date.fromisoformat(first),
            AthleteReadiness.recorded_date <= date.fromisoformat(last),
        )
        .order_by(AthleteReadiness.recorded_date, AthleteReadiness.id)
    )
    for row in readiness:
        for metric in ("hrv_rmssd_ms", "resting_hr_bpm", "sleep_duration_sec", "sleep_score"):
            value = number(getattr(row, metric))
            if value is not None:
                day = row.recorded_date.isoformat()
                snapshot = {
                    "date": day,
                    "metric": metric,
                    "value": getattr(row, metric),
                    "source": row.source,
                    "extra": row.extra_data,
                }
                add(
                    metric=metric,
                    value=value,
                    day=day,
                    provider=row.source,
                    source_id="readiness:" + str(row.id),
                    source_hash=digest(snapshot),
                    received_at=aware(row.updated_at).isoformat(),
                    method="self_report" if row.source == "MANUAL" else "device_estimate",
                    logical_key=f"{row.source}:readiness:{day}:{metric}",
                    coverage={"completeness": "unknown", "from_readiness_projection": True},
                )
    statement = (
        select(Measurement, Assessment)
        .join(Assessment, Measurement.assessment_id == Assessment.id)
        .where(
            Assessment.user_id == UUID(owner),
            Assessment.performed_at >= start,
            Assessment.performed_at < end,
        )
        .order_by(Assessment.performed_at, Measurement.id)
        .limit(2001)
    )
    measured = (await session.execute(statement)).all()
    require(len(measured) <= 2000, "ATHLETE_HISTORY_TOO_LARGE_CHOOSE_SHORTER_RANGE")
    for row, assessment in measured:
        metric = METRICS.get(row.metric_key)
        if not metric or row.unit != UNITS[metric]:
            continue
        day = aware(assessment.performed_at).astimezone(tz).date().isoformat()
        add(
            metric=metric,
            value=number(row.value_float),
            day=day,
            provider=assessment.source or "ASSESSMENT",
            source_id="assessment:" + str(row.id),
            source_hash=digest(
                {
                    "metric": row.metric_key,
                    "value": row.value_float,
                    "unit": row.unit,
                    "extra": row.extra_data,
                    "performed_at": aware(assessment.performed_at).isoformat(),
                    "assessment_type": assessment.assessment_type.value,
                }
            ),
            received_at=aware(row.created_at).isoformat(),
            method="unknown",
            logical_key=f"assessment:{row.id}:{metric}",
            protocol=assessment.title,
            sport=row.sport.value if row.sport else "",
            coverage={"completeness": "unknown", "method_needs_confirmation": True},
        )
    for row in await rows(
        select(ProviderDataRecord)
        .where(
            ProviderDataRecord.user_id == UUID(owner),
            ProviderDataRecord.provider == "POLAR",
            ProviderDataRecord.data_type.like("ATHLETE_INTAKE_%"),
            ProviderDataRecord.period_start >= start,
            ProviderDataRecord.period_start < end,
        )
        .order_by(ProviderDataRecord.period_start, ProviderDataRecord.id)
    ):
        domain = row.data_type.removeprefix("ATHLETE_INTAKE_").lower()
        day = aware(row.period_start).astimezone(tz).date().isoformat()
        source_hash = digest(row.raw_data)
        for item in polar_values(domain, row.raw_data, day):
            add(
                metric=item["metric"],
                value=item["value"],
                day=item["day"],
                provider="POLAR",
                source_id="polar_raw:" + str(row.id),
                source_hash=source_hash,
                received_at=aware(row.fetched_at).isoformat(),
                method=item["method"],
                logical_key="POLAR:" + item["logical"] + ":" + item["metric"],
                sport=item.get("sport", ""),
                protocol=item.get("protocol", ""),
                coverage=item.get("coverage"),
            )
    return sorted(result, key=lambda r: (r["start_date"], r["metric"], r["artifact_id"]))
