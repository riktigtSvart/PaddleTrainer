from copy import deepcopy

import pytest
from test_training_data_readiness_audit import audit
from test_training_data_readiness_audit import sources as _sources_fixture

from app.services.route_expected_response_model import build_route_expected_response_model
from app.services.route_input_diagnostics import build_route_input_diagnostics

sources = _sources_fixture


def diagnose(sources, **kwargs):
    source = sources[0]
    model = build_route_expected_response_model(source)
    windows = audit(sources)["routes"][0]["segments"]
    return build_route_input_diagnostics(source["routes"][0], model["routes"][0], windows, **kwargs)


def environment(sources):
    source = sources[0]["routes"][0]
    return {
        "routes": [
            {
                "route_index": 0,
                "exercise_index": 0,
                "segments": [
                    deepcopy(s["environment_context"]) | {"order_index": s["order_index"]}
                    for s in source["segments"]
                ],
            }
        ]
    }


def test_missing_details_never_certify_components_and_diagnostics_are_read_only(sources):
    original = deepcopy(sources)
    report = diagnose(sources)
    assert report["segment_count"] == 2
    assert report["component_status_counts"]["weather"] == {"COMPONENT_DETAIL_NOT_PROVIDED": 2}
    assert report["weather_feature_availability"]["status"] == "NOT_PROVIDED"
    assert report["training_authorized"] is report["pre_exercise_feature_authorized"] is False
    assert sources == original
    assert report == diagnose(sources)


def test_default_source_selection_distinguishes_not_selected_from_failed_match(sources):
    selection = {
        "weather_provider": None,
        "hydrology_provider": None,
        "waterbody_provider": None,
        "water_surface_provider": None,
        "marine_surface_provider": None,
    }
    report = diagnose(sources, provider_selection=selection)
    assert set(report["component_source_selection"].values()) == {"NOT_SELECTED"}
    selected = diagnose(
        sources, provider_selection=selection | {"weather_provider": "OPEN_METEO_HISTORICAL"}
    )
    assert selected["component_source_selection"]["weather"] == "SELECTED"
    assert selected["component_source_selection"]["wind"] == "DERIVED_FROM_SELECTED_WEATHER"
    assert selected["decision_hash"] != report["decision_hash"]


@pytest.mark.parametrize(
    "failure",
    ["WRONG_ROUTE", "DUPLICATE_ROUTE", "WRONG_ORDER", "DUPLICATE_ORDER", "MUTATED_SOURCE"],
)
def test_environment_cause_details_require_unique_current_route_order_and_source(sources, failure):
    env = environment(sources)
    if failure == "WRONG_ROUTE":
        env["routes"][0]["exercise_index"] = 99
    elif failure == "DUPLICATE_ROUTE":
        env["routes"].append(deepcopy(env["routes"][0]))
    elif failure == "WRONG_ORDER":
        env["routes"][0]["segments"][0]["order_index"] = 99
    elif failure == "DUPLICATE_ORDER":
        env["routes"][0]["segments"].append(deepcopy(env["routes"][0]["segments"][0]))
    else:
        env["routes"][0]["segments"][0]["status"] = "TRUSTED"
    report = diagnose(sources, trusted_environment=env)
    assert any("ENVIRONMENT_" in reason for reason in report["segment_blocking_reason_counts"])
    assert report["training_authorized"] is False


def test_upstream_partial_environment_acceptance_and_missing_components_are_both_visible(sources):
    for segment in sources[0]["routes"][0]["segments"]:
        segment["environment_context"].update(
            {
                "water_identity": {
                    "status": "UNAVAILABLE",
                    "available": False,
                    "trust_basis": ["WATER_ENVIRONMENT_IDENTITY_UNAVAILABLE"],
                },
                "weather": {
                    "status": "TRUSTED_WITH_LIMITATIONS",
                    "available": True,
                    "sample_id": "w1",
                    "absolute_time_delta_seconds": 120.0,
                    "surface_distance_to_sample_m": 800.0,
                    "sample": {"sample_timestamp": "2026-09-30T15:00:00+00:00"},
                },
                "hydrology": {"status": "NOT_APPLICABLE", "applicable": False},
            }
        )
    report = diagnose(sources, trusted_environment=environment(sources))
    assert report["component_status_counts"]["water_identity"] == {"UNAVAILABLE": 2}
    assert report["component_status_counts"]["hydrology"] == {"NOT_APPLICABLE": 2}
    detail = report["segment_details"]["items"][0]
    assert detail["upstream_segment_input_eligible"] is True
    assert detail["components"]["weather"]["absolute_time_delta_seconds"] == 120.0
    assert detail["components"]["weather"]["surface_distance_to_sample_m"] == 800.0
    assert detail["components"]["water_identity"]["trust_basis"] == [
        "WATER_ENVIRONMENT_IDENTITY_UNAVAILABLE"
    ]


@pytest.mark.parametrize(
    "source,status",
    [
        (
            {"provider": "OPEN_METEO", "product": "HISTORICAL", "source_type": "REANALYSIS"},
            "RETROSPECTIVE_HISTORICAL_CONTEXT",
        ),
        (
            {"provider": "INSPECT_QUERY", "source_type": "SYNTHETIC_TEST_WEATHER"},
            "SYNTHETIC_TEST_CONTEXT",
        ),
        (
            {
                "provider": "OTHER",
                "product": "FORECAST",
                "issue_time": "2026-09-29T12:00:00Z",
                "available_before_exercise_verified": True,
                "training_authorized": True,
            },
            "PRE_EXERCISE_AVAILABILITY_NOT_ESTABLISHED",
        ),
    ],
)
def test_retrospective_synthetic_and_unverified_forecasts_never_authorize_future_features(
    sources, source, status
):
    report = diagnose(sources, weather_source=source)
    availability = report["weather_feature_availability"]
    assert availability["status"] == status
    assert availability["forecast_issue_time_verified"] is False
    assert availability["available_before_exercise_verified"] is False
    assert availability["pre_exercise_feature_authorized"] is False


def test_coverage_exclusions_are_reported_even_beyond_the_first_detail_page(sources):
    source = sources[0]["routes"][0]
    model = build_route_expected_response_model(sources[0])["routes"][0]
    windows = [{"order_index": i, "grid_coverage_status": "COMPLETE"} for i in range(30)]
    windows += [
        {"order_index": 30, "grid_coverage_status": "NO_SAMPLES"},
        {"order_index": 31, "grid_coverage_status": "INVALID_WINDOW"},
    ]
    report = build_route_input_diagnostics(source, model, windows)
    assert report["segment_details"]["total_count"] == 32
    assert report["segment_details"]["returned_count"] == 25
    assert report["segment_details"]["truncated"] is True
    assert [item["order_index"] for item in report["excluded_hr_windows"]["items"]] == [30, 31]
    assert report["segment_blocking_reason_counts"]["HR_LABEL_GRID_INCOMPLETE"] == 1
    assert report["segment_blocking_reason_counts"]["HR_WINDOW_INVALID"] == 1


def test_owner_provenance_and_full_tail_commit_the_report_hash(sources):
    first = diagnose(sources, audit_source_hash="owner-one")
    second = diagnose(sources, audit_source_hash="owner-two")
    assert first["decision_hash"] != second["decision_hash"]
    changed = deepcopy(sources)
    changed[0]["routes"][0]["segments"][-1]["external_workload"]["gps_ground_speed_mps"] += 1
    assert diagnose(changed)["source_hash"] != diagnose(sources)["source_hash"]


def test_noncanonical_source_withholds_provenance(sources):
    report = diagnose(sources, provider_selection={"bad": float("nan")})
    assert report["source_hash"] is None
    assert report["status"] == "WITHHELD"
    assert report["training_authorized"] is False
