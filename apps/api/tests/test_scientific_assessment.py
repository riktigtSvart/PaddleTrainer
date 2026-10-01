from datetime import date

from app.services.scientific_assessment import (
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
        },
    }