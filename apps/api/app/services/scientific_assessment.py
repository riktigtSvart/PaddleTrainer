def build_scientific_assessment(
    coach_state: dict,
    hrv_reference_comparison: dict | None = None,
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

    return {
        "as_of_date": coach_state.get(
            "as_of_date"
        ),
        "load": {
            "interpretation": (
                load_interpretation
            ),
        },
        "readiness": {
            "interpretation": (
                readiness_interpretation
            ),
            "traceability": (
                readiness_traceability
            ),
            "objective_evidence": (
                readiness_objective_evidence
            ),
            "subjective_evidence": (
                readiness_subjective_evidence
            ),
            "context_evidence": (
                readiness_context_evidence
            ),
            "hrv_reference_comparison": (
                hrv_reference_comparison
            ),
        },
    }