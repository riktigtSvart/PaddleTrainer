from app.services.capacity_observations import (
    build_capacity_evidence,
)


def test_build_capacity_evidence_preserves_sources():
    observations = [
        {
            "capacity_type": "GENERAL_AEROBIC",
            "sport": None,
            "source": "ASSESSMENT",
            "value": 68.2,
            "confidence": 0.95,
        },
        {
            "capacity_type": "GENERAL_AEROBIC",
            "sport": None,
            "source": "MANUAL",
            "value": 68.2,
            "confidence": 0.5,
        },
    ]

    evidence = build_capacity_evidence(
        observations
    )

    assert len(evidence["groups"]) == 1

    group = evidence["groups"][0]

    assert (
        group["capacity_type"]
        == "GENERAL_AEROBIC"
    )
    assert group["sport"] is None

    assert [
        item["source"]
        for item in group["observations"]
    ] == [
        "ASSESSMENT",
        "MANUAL",
    ]