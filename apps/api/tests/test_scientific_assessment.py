from datetime import date

from app.services.scientific_assessment import (
    build_personal_reference_evidence,
    build_scientific_assessment,
)


def test_scientific_assessment_describes_method_dependent_load():
    coach_state = {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "pattern": {
                "state": "METHODS_DIVERGE",
                "raw_acute_vs_chronic": "ABOVE",
                "smoothed_acute_vs_chronic": "BELOW",
            },
        },
    }

    result = build_scientific_assessment(
        coach_state
    )

    assert result == {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "interpretation": {
                "state": "METHOD_DEPENDENT",
                "raw_acute_vs_chronic": (
                    "ABOVE"
                ),
                "smoothed_acute_vs_chronic": (
                    "BELOW"
                ),
            },
        },
        "readiness": {
            "interpretation": None,
            "traceability": None,
            "objective_evidence": None,
            "subjective_evidence": None,
            "context_evidence": None,
            "hrv_reference_comparison": None,
            "sleep_duration_reference_comparison": None,
        },
    }


def test_scientific_assessment_does_not_infer_load_alignment_from_missing_pattern():
    coach_state = {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "pattern": None,
        },
    }

    result = build_scientific_assessment(
        coach_state
    )

    assert result == {
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
            "hrv_reference_comparison": None,
            "sleep_duration_reference_comparison": None,
        },
    }


def test_scientific_assessment_marks_readiness_as_partial_when_evidence_gaps_exist():
    coach_state = {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "pattern": None,
        },
        "readiness": {
            "evidence": {
                "gaps": [
                    "ILLNESS_STATUS_UNKNOWN",
                    "TRAVEL_STATUS_UNKNOWN",
                ],
            },
        },
    }

    result = build_scientific_assessment(
        coach_state
    )

    assert result == {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "interpretation": None,
        },
        "readiness": {
            "interpretation": {
                "state": "PARTIAL_EVIDENCE",
                "gaps": [
                    "ILLNESS_STATUS_UNKNOWN",
                    "TRAVEL_STATUS_UNKNOWN",
                ],
            },
            "traceability": None,
            "objective_evidence": None,
            "subjective_evidence": None,
            "context_evidence": None,
            "hrv_reference_comparison": None,
            "sleep_duration_reference_comparison": None,
        },
    }


def test_scientific_assessment_does_not_infer_complete_readiness_from_no_gaps():
    coach_state = {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "pattern": None,
        },
        "readiness": {
            "evidence": {
                "gaps": [],
            },
        },
    }

    result = build_scientific_assessment(
        coach_state
    )

    assert result == {
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
            "hrv_reference_comparison": None,
            "sleep_duration_reference_comparison": None,
        },
    }


def test_scientific_assessment_preserves_missing_metric_provenance_as_traceability_state():
    coach_state = {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "pattern": None,
        },
        "readiness": {
            "evidence": {
                "gaps": [],
                "metric_provenance_state": (
                    "UNAVAILABLE"
                ),
            },
        },
    }

    result = build_scientific_assessment(
        coach_state
    )

    assert result == {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "interpretation": None,
        },
        "readiness": {
            "interpretation": None,
            "traceability": {
                "state": (
                    "METRIC_PROVENANCE_UNAVAILABLE"
                ),
            },
            "objective_evidence": None,
            "subjective_evidence": None,
            "context_evidence": None,
            "hrv_reference_comparison": None,
            "sleep_duration_reference_comparison": None,
        },
    }


def test_scientific_assessment_preserves_available_objective_readiness_evidence():
    coach_state = {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "pattern": None,
        },
        "readiness": {
            "evidence": {
                "gaps": [],
            },
            "view": {
                "presence": {
                    "objective": {
                        "available_metrics": [
                            "hrv_rmssd_ms",
                            "sleep_duration_sec",
                            "sleep_score",
                        ],
                        "no_data_metrics": [],
                    },
                },
            },
        },
    }

    result = build_scientific_assessment(
        coach_state
    )

    assert result == {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "interpretation": None,
        },
        "readiness": {
            "interpretation": None,
            "traceability": None,
            "objective_evidence": {
                "state": (
                    "OBJECTIVE_EVIDENCE_AVAILABLE"
                ),
                "metrics": [
                    "hrv_rmssd_ms",
                    "sleep_duration_sec",
                    "sleep_score",
                ],
            },
            "subjective_evidence": None,
            "context_evidence": None,
            "hrv_reference_comparison": None,
            "sleep_duration_reference_comparison": None,
        },
    }


def test_scientific_assessment_preserves_available_subjective_readiness_evidence():
    coach_state = {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "pattern": None,
        },
        "readiness": {
            "evidence": {
                "gaps": [],
            },
            "view": {
                "presence": {
                    "subjective": {
                        "available_metrics": [
                            "energy_score",
                            "fatigue_score",
                            "soreness_score",
                            "stress_score",
                        ],
                    },
                },
            },
        },
    }

    result = build_scientific_assessment(
        coach_state
    )

    assert result == {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "interpretation": None,
        },
        "readiness": {
            "interpretation": None,
            "traceability": None,
            "objective_evidence": None,
            "subjective_evidence": {
                "state": (
                    "SUBJECTIVE_EVIDENCE_AVAILABLE"
                ),
                "metrics": [
                    "energy_score",
                    "fatigue_score",
                    "soreness_score",
                    "stress_score",
                ],
            },
            "context_evidence": None,
            "hrv_reference_comparison": None,
            "sleep_duration_reference_comparison": None,
        },
    }


def test_scientific_assessment_preserves_available_context_readiness_evidence():
    coach_state = {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "pattern": None,
        },
        "readiness": {
            "evidence": {
                "gaps": [],
            },
            "view": {
                "presence": {
                    "objective_context": {
                        "available_metrics": [
                            "background_hr_median_bpm",
                        ],
                    },
                },
            },
        },
    }

    result = build_scientific_assessment(
        coach_state
    )

    assert result == {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "interpretation": None,
        },
        "readiness": {
            "interpretation": None,
            "traceability": None,
            "objective_evidence": None,
            "subjective_evidence": None,
            "context_evidence": {
                "state": "CONTEXT_EVIDENCE_AVAILABLE",
                "metrics": [
                    "background_hr_median_bpm",
                ],
            },
            "hrv_reference_comparison": None,
            "sleep_duration_reference_comparison": None,
        },
    }


def test_scientific_assessment_preserves_hrv_personal_reference_comparison():
    coach_state = {
        "as_of_date": date(2026, 9, 30),
        "load": {
            "pattern": None,
        },
        "readiness": {
            "evidence": {
                "gaps": [],
            },
        },
    }

    comparison = {
        "metric_key": "hrv_rmssd_ms",
        "current_value": 58.4,
        "reference_value": 54.0,
        "relation": (
            "ABOVE_PERSONAL_REFERENCE"
        ),
        "reference_method": "RECENT_MEDIAN",
        "reference_sample_count": 6,
    }

    result = build_scientific_assessment(
        coach_state=coach_state,
        hrv_reference_comparison=comparison,
    )

    assert result[
        "readiness"
    ][
        "hrv_reference_comparison"
    ] == comparison

    assert result["readiness"][
               "personal_reference_evidence"
           ] == {
               "hrv_rmssd_ms": (
                   build_personal_reference_evidence(
                       comparison
                   )
               ),
           }


def test_scientific_assessment_preserves_sleep_duration_reference_comparison():
    comparison = {
        "metric_key": "sleep_duration_sec",
        "current_value": 27600.0,
        "reference_value": 20790.0,
        "relation": "ABOVE_PERSONAL_REFERENCE",
        "reference_method": "RECENT_MEDIAN",
        "reference_sample_count": 1,
        "reference_sample_support": {
            "sample_count": 1,
            "state": "SINGLE_SAMPLE",
        },
    }

    result = build_scientific_assessment(
        coach_state={
            "as_of_date": "2026-09-30",
        },
        sleep_duration_reference_comparison=(
            comparison
        ),
    )

    assert (
        result["readiness"][
            "sleep_duration_reference_comparison"
        ]
        == comparison
    )

    assert result["readiness"][
               "personal_reference_evidence"
           ] == {
               "sleep_duration_sec": (
                   build_personal_reference_evidence(
                       comparison
                   )
               ),
           }


def test_personal_reference_evidence_describes_available_hrv_comparison_facts():
    comparison = {
        "metric_key": "hrv_rmssd_ms",
        "current_value": 58.4,
        "reference_value": 54.0,
        "relation": "ABOVE_PERSONAL_REFERENCE",
        "reference_method": "RECENT_MEDIAN",
        "reference_sample_count": 6,
        "reference_sample_support": {
            "sample_count": 6,
            "state": "MULTIPLE_SAMPLES",
        },
        "reference_median_absolute_deviation": 7.5,
        "difference_from_reference": 4.4,
        "relative_difference_from_reference": 0.0814814815,
        "difference_in_reference_mad_units": 0.5866666667,
    }

    result = build_personal_reference_evidence(
        comparison
    )

    assert result == {
        "metric_key": "hrv_rmssd_ms",
        "current_value_available": True,
        "reference_value_available": True,
        "reference_sample_count": 6,
        "reference_sample_support": {
            "sample_count": 6,
            "state": "MULTIPLE_SAMPLES",
        },
        "reference_variability_available": True,
        "absolute_difference_available": True,
        "relative_difference_available": True,
        "mad_scaled_difference_available": True,
    }


def test_personal_reference_evidence_preserves_missing_variability_for_single_sample_sleep():
    comparison = {
        "metric_key": "sleep_duration_sec",
        "current_value": 27600.0,
        "reference_value": 20790.0,
        "relation": "ABOVE_PERSONAL_REFERENCE",
        "reference_method": "RECENT_MEDIAN",
        "reference_sample_count": 1,
        "reference_sample_support": {
            "sample_count": 1,
            "state": "SINGLE_SAMPLE",
        },
        "reference_median_absolute_deviation": None,
        "difference_from_reference": 6810.0,
        "relative_difference_from_reference": 0.3275613276,
        "difference_in_reference_mad_units": None,
    }

    result = build_personal_reference_evidence(
        comparison
    )

    assert result == {
        "metric_key": "sleep_duration_sec",
        "current_value_available": True,
        "reference_value_available": True,
        "reference_sample_count": 1,
        "reference_sample_support": {
            "sample_count": 1,
            "state": "SINGLE_SAMPLE",
        },
        "reference_variability_available": False,
        "absolute_difference_available": True,
        "relative_difference_available": True,
        "mad_scaled_difference_available": False,
    }


def test_scientific_assessment_preserves_hrv_trend_evidence():
    trend_evidence = {
        "metric_key": "hrv_rmssd_ms",
        "transform": "NATURAL_LOG",
        "window_days": 7,
        "sample_count": 5,
        "sample_support": {
            "sample_count": 5,
            "state": "MULTIPLE_SAMPLES",
        },
        "current_ln_rmssd": 4.067316815,
        "rolling_mean_ln_rmssd": 4.0123456789,
        "rolling_cv_percent": 2.4,
    }

    result = build_scientific_assessment(
        coach_state={
            "as_of_date": date(2026, 9, 30),
        },
        hrv_trend_evidence=trend_evidence,
    )

    assert result["readiness"][
        "hrv_trend_evidence"
    ] == trend_evidence