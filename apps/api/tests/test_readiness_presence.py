from types import SimpleNamespace

from app.api.routes.readiness import (
    AthleteReadinessUpdate,
    merge_subjective_reported_fields,
)
from app.services.readiness_evidence import (
    build_subjective_presence, build_objective_context_presence,
)


def test_explicit_false_is_distinct_from_missing_boolean():
    missing_payload = AthleteReadinessUpdate()

    missing_extra_data = merge_subjective_reported_fields(
        {},
        missing_payload,
    )

    missing_readiness = SimpleNamespace(
        energy_score=None,
        fatigue_score=None,
        stress_score=None,
        soreness_score=None,
        illness=False,
        travel=False,
        extra_data=missing_extra_data,
    )

    missing_presence = build_subjective_presence(
        missing_readiness
    )

    assert (
        missing_presence["illness"]["status"]
        == "NO_DATA"
    )
    assert (
        missing_presence["illness"]["explicit"]
        is False
    )

    explicit_payload = AthleteReadinessUpdate(
        illness=False,
    )

    explicit_extra_data = (
        merge_subjective_reported_fields(
            {},
            explicit_payload,
        )
    )

    explicit_readiness = SimpleNamespace(
        energy_score=None,
        fatigue_score=None,
        stress_score=None,
        soreness_score=None,
        illness=False,
        travel=False,
        extra_data=explicit_extra_data,
    )

    explicit_presence = build_subjective_presence(
        explicit_readiness
    )

    assert (
        explicit_presence["illness"]["status"]
        == "AVAILABLE"
    )
    assert (
        explicit_presence["illness"]["explicit"]
        is True
    )


def test_legacy_numeric_subjective_values_are_inferred_but_booleans_are_not():
    readiness = SimpleNamespace(
        energy_score=7.0,
        fatigue_score=4.0,
        stress_score=2.0,
        soreness_score=5.0,
        illness=False,
        travel=False,
        extra_data={},
    )

    presence = build_subjective_presence(
        readiness
    )

    for field_name in (
        "energy_score",
        "fatigue_score",
        "stress_score",
        "soreness_score",
    ):
        assert (
            presence[field_name]["status"]
            == "AVAILABLE"
        )
        assert (
            presence[field_name]["explicit"]
            is False
        )
        assert (
            presence[field_name]["legacy_inferred"]
            is True
        )

    for field_name in (
        "illness",
        "travel",
    ):
        assert (
            presence[field_name]["status"]
            == "NO_DATA"
        )
        assert (
            presence[field_name]["explicit"]
            is False
        )
        assert (
            presence[field_name]["legacy_inferred"]
            is False
        )


def test_missing_known_objective_context_metric_is_no_data():
    readiness = SimpleNamespace(
        extra_data={},
    )

    presence = build_objective_context_presence(
        readiness
    )

    assert (
        presence[
            "background_hr_median_bpm"
        ]["status"]
        == "NO_DATA"
    )


def test_explicit_null_removes_subjective_reported_presence():
        payload = AthleteReadinessUpdate(
            energy_score=None,
        )

        extra_data = (
            merge_subjective_reported_fields(
                {
                    "subjective_reported_fields": [
                        "energy_score",
                        "illness",
                    ],
                },
                payload,
            )
        )

        reported_fields = extra_data[
            "subjective_reported_fields"
        ]

        assert "energy_score" not in reported_fields
        assert "illness" in reported_fields