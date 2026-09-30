from app.models.entities import AthleteReadiness


SUBJECTIVE_FIELDS = (
    "energy_score",
    "fatigue_score",
    "stress_score",
    "soreness_score",
    "illness",
    "travel",
)


OBJECTIVE_FIELDS = (
    "hrv_rmssd_ms",
    "sleep_duration_sec",
    "sleep_score",
)

OBJECTIVE_CONTEXT_METRICS = (
    "background_hr_median_bpm",
)

def build_readiness_evidence(
    readiness: AthleteReadiness,
) -> dict:
    extra_data = readiness.extra_data or {}

    return {
        "recorded_date": readiness.recorded_date.isoformat(),
        "source": readiness.source,
        "objective": {
            "hrv_rmssd_ms": (
                readiness.hrv_rmssd_ms
            ),
            "sleep_duration_sec": (
                readiness.sleep_duration_sec
            ),
            "sleep_score": (
                readiness.sleep_score
            ),
        },
        "objective_context": (
            extra_data.get(
                "objective_context",
                {}
            )
        ),
        "subjective": {
            "energy_score": (
                readiness.energy_score
            ),
            "fatigue_score": (
                readiness.fatigue_score
            ),
            "stress_score": (
                readiness.stress_score
            ),
            "soreness_score": (
                readiness.soreness_score
            ),
            "illness": readiness.illness,
            "travel": readiness.travel,
        },
        "provenance": (
            extra_data.get(
                "objective_measurements",
                {}
            )
        ),
        "presence": {
            "objective": (
                build_objective_presence(
                    readiness
                )
            ),
            "objective_context": (
                build_objective_context_presence(
                    readiness
                )
            ),
            "subjective": (
                build_subjective_presence(
                    readiness
                )
            ),
        },
    }

def build_objective_presence(
    readiness: AthleteReadiness,
) -> dict:
    result = {}

    for field_name in OBJECTIVE_FIELDS:
        value = getattr(
            readiness,
            field_name,
        )

        result[field_name] = {
            "status": (
                "AVAILABLE"
                if value is not None
                else "NO_DATA"
            ),
        }

    return result


def build_objective_context_presence(
    readiness: AthleteReadiness,
) -> dict:
    extra_data = readiness.extra_data or {}

    context = extra_data.get(
        "objective_context",
        {},
    )

    result = {}

    for metric_key in OBJECTIVE_CONTEXT_METRICS:
        item = context.get(metric_key)

        value = (
            item.get("value")
            if isinstance(item, dict)
            else None
        )

        result[metric_key] = {
            "status": (
                "AVAILABLE"
                if value is not None
                else "NO_DATA"
            ),
        }

    return result


def build_subjective_presence(
    readiness: AthleteReadiness,
) -> dict:
    extra_data = readiness.extra_data or {}

    reported_fields = set(
        extra_data.get(
            "subjective_reported_fields",
            [],
        )
    )

    result = {}

    for field_name in SUBJECTIVE_FIELDS:
        value = getattr(
            readiness,
            field_name,
        )

        explicit = (
            field_name in reported_fields
        )

        # Legacy compatibility:
        # a nullable numeric subjective mezőnél
        # a non-None érték régi rekordban is
        # valódi adatot jelenthet.
        legacy_inferred = (
            field_name
            not in {"illness", "travel"}
            and value is not None
            and not explicit
        )

        available = (
            explicit
            or legacy_inferred
        )

        result[field_name] = {
            "status": (
                "AVAILABLE"
                if available
                else "NO_DATA"
            ),
            "explicit": explicit,
            "legacy_inferred": (
                legacy_inferred
            ),
        }

    return result