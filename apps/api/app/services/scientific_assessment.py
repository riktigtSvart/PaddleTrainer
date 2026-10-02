def build_personal_reference_evidence(
    comparison: dict | None,
) -> dict | None:
    if comparison is None:
        return None

    return {
        "metric_key": comparison.get(
            "metric_key"
        ),
        "current_value_available": (
            comparison.get(
                "current_value"
            )
            is not None
        ),
        "reference_value_available": (
            comparison.get(
                "reference_value"
            )
            is not None
        ),
        "reference_sample_count": (
            comparison.get(
                "reference_sample_count",
                0,
            )
        ),
        "reference_sample_support": (
            comparison.get(
                "reference_sample_support"
            )
        ),
        "reference_variability_available": (
            comparison.get(
                "reference_median_absolute_deviation"
            )
            is not None
        ),
        "absolute_difference_available": (
            comparison.get(
                "difference_from_reference"
            )
            is not None
        ),
        "relative_difference_available": (
            comparison.get(
                "relative_difference_from_reference"
            )
            is not None
        ),
        "mad_scaled_difference_available": (
            comparison.get(
                "difference_in_reference_mad_units"
            )
            is not None
        ),
    }


def build_scientific_assessment(
    coach_state: dict,
    hrv_reference_comparison: dict | None = None,
    sleep_duration_reference_comparison: dict | None = None,
) -> dict:
    load = coach_state.get(
        "load",
        {},
    )

    load_pattern = load.get(
        "pattern"
    )

    load_interpretation = None

    if (
        load_pattern is not None
        and load_pattern.get("state")
        == "METHODS_DIVERGE"
    ):
        load_interpretation = {
            "state": "METHOD_DEPENDENT",
            "raw_acute_vs_chronic": (
                load_pattern.get(
                    "raw_acute_vs_chronic"
                )
            ),
            "smoothed_acute_vs_chronic": (
                load_pattern.get(
                    "smoothed_acute_vs_chronic"
                )
            ),
        }

    readiness = coach_state.get(
        "readiness",
        {},
    )

    readiness_evidence = readiness.get(
        "evidence"
    )

    readiness_interpretation = None

    readiness_traceability = None

    readiness_objective_evidence = None

    readiness_subjective_evidence = None

    readiness_context_evidence = None

    readiness_view = readiness.get(
        "view",
        {},
    ) or {}

    objective_presence = (
        readiness_view.get(
            "presence",
            {},
        ).get(
            "objective",
            {},
        )
    )

    subjective_presence = (
        readiness_view.get(
            "presence",
            {},
        ).get(
            "subjective",
            {},
        )
    )

    context_presence = (
        readiness_view.get(
            "presence",
            {},
        ).get(
            "objective_context",
            {},
        )
    )

    context_available_metrics = (
        context_presence.get(
            "available_metrics",
            [],
        )
    )

    if context_available_metrics:
        readiness_context_evidence = {
            "state": "CONTEXT_EVIDENCE_AVAILABLE",
            "metrics": list(
                context_available_metrics
            ),
        }

    subjective_available_metrics = (
        subjective_presence.get(
            "available_metrics",
            [],
        )
    )

    if subjective_available_metrics:
        readiness_subjective_evidence = {
            "state": (
                "SUBJECTIVE_EVIDENCE_AVAILABLE"
            ),
            "metrics": list(
                subjective_available_metrics
            ),
        }

    objective_available_metrics = (
        objective_presence.get(
            "available_metrics",
            [],
        )
    )

    if objective_available_metrics:
        readiness_objective_evidence = {
            "state": (
                "OBJECTIVE_EVIDENCE_AVAILABLE"
            ),
            "metrics": list(
                objective_available_metrics
            ),
        }

    if readiness_evidence is not None:
        provenance_state = (
            readiness_evidence.get(
                "metric_provenance_state"
            )
        )

        if provenance_state == "UNAVAILABLE":
            readiness_traceability = {
                "state": "METRIC_PROVENANCE_UNAVAILABLE",
            }

    if readiness_evidence is not None:
        gaps = readiness_evidence.get(
            "gaps",
            [],
        )

        if gaps:
            readiness_interpretation = {
                "state": "PARTIAL_EVIDENCE",
                "gaps": list(gaps),
            }

    personal_reference_evidence = None

    if hrv_reference_comparison is not None:
        metric_key = hrv_reference_comparison.get(
            "metric_key"
        )

        if metric_key is not None:
            personal_reference_evidence = {
                metric_key: (
                    build_personal_reference_evidence(
                        hrv_reference_comparison
                    )
                ),
            }

    if sleep_duration_reference_comparison is not None:
        metric_key = (
            sleep_duration_reference_comparison.get(
                "metric_key"
            )
        )

        if metric_key is not None:
            if personal_reference_evidence is None:
                personal_reference_evidence = {}

            personal_reference_evidence[
                metric_key
            ] = build_personal_reference_evidence(
                sleep_duration_reference_comparison
            )

    readiness_result = {
        "interpretation": readiness_interpretation,
        "traceability": readiness_traceability,
        "objective_evidence": readiness_objective_evidence,
        "subjective_evidence": readiness_subjective_evidence,
        "context_evidence": readiness_context_evidence,
        "hrv_reference_comparison": (
            hrv_reference_comparison
        ),
        "sleep_duration_reference_comparison": (
            sleep_duration_reference_comparison
        ),
    }

    if personal_reference_evidence is not None:
        readiness_result[
            "personal_reference_evidence"
        ] = personal_reference_evidence

    return {
        "as_of_date": coach_state.get(
            "as_of_date"
        ),
        "load": {
            "interpretation": load_interpretation,
        },
        "readiness": readiness_result,
    }