def build_athlete_state_scientific_view(
    scientific_assessment: dict,
) -> dict:
    training_load = scientific_assessment.get(
        "load",
        {},
    )

    recovery_readiness = scientific_assessment.get(
        "readiness",
        {},
    )

    readiness_interpretation = (
        recovery_readiness.get(
            "interpretation"
        )
        or {}
    )

    objective_evidence = (
        recovery_readiness.get(
            "objective_evidence"
        )
        or {}
    )

    subjective_evidence = (
        recovery_readiness.get(
            "subjective_evidence"
        )
        or {}
    )

    context_evidence = (
        recovery_readiness.get(
            "context_evidence"
        )
        or {}
    )

    personal_reference_evidence = (
        recovery_readiness.get(
            "personal_reference_evidence"
        )
        or {}
    )

    evidence_inventory = {
        "gaps": list(
            readiness_interpretation.get(
                "gaps",
                [],
            )
        ),
        "traceability": recovery_readiness.get(
            "traceability"
        ),
        "objective_metrics": list(
            objective_evidence.get(
                "metrics",
                [],
            )
        ),
        "subjective_metrics": list(
            subjective_evidence.get(
                "metrics",
                [],
            )
        ),
        "context_metrics": list(
            context_evidence.get(
                "metrics",
                [],
            )
        ),
        "personal_reference_metrics": list(
            personal_reference_evidence.keys()
        ),
    }

    return {
        "as_of_date": scientific_assessment.get(
            "as_of_date"
        ),
        "training_load": training_load,
        "recovery_readiness": recovery_readiness,
        "evidence_inventory": evidence_inventory,
    }