from datetime import date

from app.services.athlete_state_scientific_view import (
    build_athlete_state_scientific_view,
)


def test_athlete_state_scientific_view_preserves_available_scientific_state():
    scientific_assessment = {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "interpretation": {
                "state": "METHOD_DEPENDENT",
                "raw_acute_vs_chronic": "ABOVE",
                "smoothed_acute_vs_chronic": "BELOW",
            },
        },
        "readiness": {
            "interpretation": {
                "state": "PARTIAL_EVIDENCE",
                "gaps": [
                    "ILLNESS_STATUS_UNKNOWN",
                    "TRAVEL_STATUS_UNKNOWN",
                ],
            },
            "traceability": {
                "state": "METRIC_PROVENANCE_UNAVAILABLE",
            },
            "objective_evidence": {
                "state": "OBJECTIVE_EVIDENCE_AVAILABLE",
                "metrics": [
                    "hrv_rmssd_ms",
                    "sleep_duration_sec",
                    "sleep_score",
                ],
            },
            "subjective_evidence": {
                "state": "SUBJECTIVE_EVIDENCE_AVAILABLE",
                "metrics": [
                    "energy_score",
                    "fatigue_score",
                    "soreness_score",
                    "stress_score",
                ],
            },
            "context_evidence": None,
            "hrv_reference_comparison": {
                "metric_key": "hrv_rmssd_ms",
                "current_value": 58.4,
                "reference_value": 54.0,
            },
            "sleep_duration_reference_comparison": {
                "metric_key": "sleep_duration_sec",
                "current_value": 27600.0,
                "reference_value": 20790.0,
            },
            "personal_reference_evidence": {
                "hrv_rmssd_ms": {
                    "metric_key": "hrv_rmssd_ms",
                    "reference_sample_count": 6,
                },
                "sleep_duration_sec": {
                    "metric_key": "sleep_duration_sec",
                    "reference_sample_count": 1,
                },
            },
        },
    }

    result = build_athlete_state_scientific_view(
        scientific_assessment
    )

    assert result == {
        "as_of_date": date(2026, 9, 30),
        "training_load": {
            "interpretation": {
                "state": "METHOD_DEPENDENT",
                "raw_acute_vs_chronic": "ABOVE",
                "smoothed_acute_vs_chronic": "BELOW",
            },
        },
        "recovery_readiness": {
            "interpretation": {
                "state": "PARTIAL_EVIDENCE",
                "gaps": [
                    "ILLNESS_STATUS_UNKNOWN",
                    "TRAVEL_STATUS_UNKNOWN",
                ],
            },
            "traceability": {
                "state": "METRIC_PROVENANCE_UNAVAILABLE",
            },
            "objective_evidence": {
                "state": "OBJECTIVE_EVIDENCE_AVAILABLE",
                "metrics": [
                    "hrv_rmssd_ms",
                    "sleep_duration_sec",
                    "sleep_score",
                ],
            },
            "subjective_evidence": {
                "state": "SUBJECTIVE_EVIDENCE_AVAILABLE",
                "metrics": [
                    "energy_score",
                    "fatigue_score",
                    "soreness_score",
                    "stress_score",
                ],
            },
            "context_evidence": None,
            "hrv_reference_comparison": {
                "metric_key": "hrv_rmssd_ms",
                "current_value": 58.4,
                "reference_value": 54.0,
            },
            "sleep_duration_reference_comparison": {
                "metric_key": "sleep_duration_sec",
                "current_value": 27600.0,
                "reference_value": 20790.0,
            },
            "personal_reference_evidence": {
                "hrv_rmssd_ms": {
                    "metric_key": "hrv_rmssd_ms",
                    "reference_sample_count": 6,
                },
                "sleep_duration_sec": {
                    "metric_key": "sleep_duration_sec",
                    "reference_sample_count": 1,
                },
            },
        },
        "evidence_inventory": {
            "gaps": [
                "ILLNESS_STATUS_UNKNOWN",
                "TRAVEL_STATUS_UNKNOWN",
            ],
            "traceability": {
                "state": "METRIC_PROVENANCE_UNAVAILABLE",
            },
            "objective_metrics": [
                "hrv_rmssd_ms",
                "sleep_duration_sec",
                "sleep_score",
            ],
            "subjective_metrics": [
                "energy_score",
                "fatigue_score",
                "soreness_score",
                "stress_score",
            ],
            "context_metrics": [],
            "personal_reference_metrics": [
                "hrv_rmssd_ms",
                "sleep_duration_sec",
            ],
        },
    }


def test_athlete_state_scientific_view_preserves_empty_evidence_inventory():
    scientific_assessment = {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "interpretation": None,
        },
        "readiness": {
            "interpretation": None,
            "traceability": None,
            "objective_evidence": None,
            "subjective_evidence": None,
            "context_evidence": None,
        },
    }

    result = build_athlete_state_scientific_view(
        scientific_assessment
    )

    assert result["evidence_inventory"] == {
        "gaps": [],
        "traceability": None,
        "objective_metrics": [],
        "subjective_metrics": [],
        "context_metrics": [],
        "personal_reference_metrics": [],
    }