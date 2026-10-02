def build_capacity_evidence(
    capacity_items: list[dict],
) -> list[dict]:
    return [
        {
            "capacity_type": item.get(
                "capacity_type"
            ),
            "sport": item.get(
                "sport"
            ),
            "source": item.get(
                "source"
            ),
            "assessment_link_available": (
                item.get(
                    "assessment_id"
                )
                is not None
            ),
            "measurement_link_available": (
                item.get(
                    "measurement_id"
                )
                is not None
            ),
            "confidence_available": (
                item.get(
                    "confidence"
                )
                is not None
            ),
            "estimated_at_available": (
                item.get(
                    "estimated_at"
                )
                is not None
            ),
            "age_days_available": (
                item.get(
                    "age_days"
                )
                is not None
            ),
            "age_days": item.get(
                "age_days"
            ),
        }
        for item in capacity_items
    ]


def build_athlete_state_scientific_view(
    scientific_assessment: dict,
    capacity_state: list[dict] | None = None,
) -> dict:
    capacity_items = list(
        capacity_state or []
    )

    capacity_evidence = (
        build_capacity_evidence(
            capacity_items
        )
    )

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
        "capacity_dimensions": [
            {
                "capacity_type": item.get(
                    "capacity_type"
                ),
                "sport": item.get(
                    "sport"
                ),
            }
            for item in capacity_items
        ],
    }

    return {
        "as_of_date": scientific_assessment.get(
            "as_of_date"
        ),
        "training_load": training_load,
        "recovery_readiness": recovery_readiness,
        "evidence_inventory": evidence_inventory,
        "capacity": {
            "available": bool(capacity_items),
            "items": capacity_items,
            "evidence": capacity_evidence,
        },
    }