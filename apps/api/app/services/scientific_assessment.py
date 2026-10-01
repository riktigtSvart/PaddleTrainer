def build_scientific_assessment(
    coach_state: dict,
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
        },
    }