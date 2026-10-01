from datetime import date

from app.services.coach_context import (
    build_coach_assessment,
    build_coach_context,
    build_coach_inputs,
    build_descriptive_flags,
    build_interpretation_facts,
    build_interpretation_signals,
    build_today_plan,
    build_readiness_coach_view,
    build_readiness_presence_summary,
    build_readiness_provenance_summary,
)


def test_build_today_plan_selects_snapshot_date_workouts():
    monday_workout = {
        "id": "workout-1",
        "date": date(2026, 9, 28),
        "sport": "KAYAK",
        "title": "30' zone 2 paddling",
    }

    today_workout = {
        "id": "workout-2",
        "date": date(2026, 9, 30),
        "sport": "KAYAK",
        "title": "8km kayaking",
    }

    plan_context = {
        "as_of_date": date(2026, 9, 30),
        "current_week": {
            "week_start": date(2026, 9, 28),
            "week_end": date(2026, 10, 4),
            "planned_workouts": [
                monday_workout,
                today_workout,
            ],
        },
    }

    today_plan = build_today_plan(
        plan_context=plan_context,
        as_of_date=date(2026, 9, 30),
    )

    assert today_plan == {
        "date": date(2026, 9, 30),
        "planned_workouts": [
            today_workout,
        ],
    }


def test_build_coach_context_combines_state_and_today_plan():
    today_workout = {
        "id": "workout-2",
        "date": date(2026, 9, 30),
        "sport": "KAYAK",
        "title": "8km kayaking",
    }

    athlete_state = {
        "as_of_date": date(2026, 9, 30),
        "training_load": {
            "marker": "load",
        },
        "readiness": {
            "marker": "readiness",
        },
        "plan_context": {
            "as_of_date": date(2026, 9, 30),
            "current_week": {
                "week_start": date(2026, 9, 28),
                "week_end": date(2026, 10, 4),
                "planned_workouts": [
                    today_workout,
                ],
            },
        },
    }

    coach_context = build_coach_context(
        athlete_state=athlete_state,
        as_of_date=date(2026, 9, 30),
    )

    assert (
        coach_context["athlete_state"]
        is athlete_state
    )

    assert coach_context["today_plan"] == {
        "date": date(2026, 9, 30),
        "planned_workouts": [
            today_workout,
        ],
    }


def test_build_coach_inputs_preserves_source_layers():
    today_plan = {
        "date": date(2026, 9, 30),
        "planned_workouts": [
            {
                "title": "8km kayaking",
            },
        ],
    }

    training_load = {
        "marker": "load",
    }

    readiness = {
        "marker": "readiness",
    }

    capacity_evidence = {
        "marker": "capacity",
    }

    background_evidence = {
        "marker": "background",
    }

    response_trajectories = {
        "marker": "responses",
    }

    active_periods = [
        {
            "period_type": "MESOCYCLE",
            "title": "Őszi alapozó ciklus 1",
        },
    ]

    coach_context = {
        "as_of_date": date(2026, 9, 30),
        "today_plan": today_plan,
        "athlete_state": {
            "training_load": training_load,
            "readiness": readiness,
            "capacity_evidence": (
                capacity_evidence
            ),
            "long_term_background_evidence": (
                background_evidence
            ),
            "response_trajectories": (
                response_trajectories
            ),
            "plan_context": {
                "active_periods": active_periods,
            },
        },
    }

    inputs = build_coach_inputs(
        coach_context
    )

    assert inputs == {
        "as_of_date": date(2026, 9, 30),
        "plan": {
            "today": today_plan,
            "active_periods": active_periods,
        },
        "athlete": {
            "training_load": training_load,
            "readiness": readiness,
            "capacity_evidence": (
                capacity_evidence
            ),
            "long_term_background_evidence": (
                background_evidence
            ),
            "response_trajectories": (
                response_trajectories
            ),
        },
    }


def test_build_interpretation_facts_is_descriptive():
    coach_inputs = {
        "as_of_date": date(2026, 9, 30),
        "plan": {
            "today": {
                "date": date(2026, 9, 30),
                "planned_workouts": [
                    {
                        "id": "workout-1",
                        "sport": "KAYAK",
                        "title": "8km kayaking",
                        "execution": {
                            "has_actual": False,
                            "link_source": None,
                        },
                    },
                ],
            },
            "active_periods": [
                {
                    "period_type": "MESOCYCLE",
                    "title": "Őszi alapozó ciklus 1",
                    "objectives": [
                        {
                            "objective_type": "ENDURANCE",
                            "weight": 0.6,
                        },
                        {
                            "objective_type": "STRENGTH",
                            "weight": 0.2,
                        },
                        {
                            "objective_type": "TECHNIQUE",
                            "weight": 0.2,
                        },
                    ],
                },
            ],
        },
        "athlete": {
            "training_load": {
                "acute": {
                    "weekly_load": 151.53,
                },
                "chronic": {
                    "weekly_load": 110.09,
                },
                "smoothed": {
                    "method": "NORMALIZED_EWMA",
                    "acute": {
                        "weekly_equivalent": 103.38,
                    },
                    "chronic": {
                        "weekly_equivalent": 221.69,
                    },
                },
            },
            "readiness": {
                "source": "MANUAL",
                "objective": {
                    "hrv_rmssd_ms": 58.4,
                },
                "objective_context": {
                    "background_hr_median_bpm": None,
                },
                "subjective": {
                    "fatigue_score": 4.0,
                    "illness": False,
                },
                "presence": {
                    "objective": {
                        "hrv_rmssd_ms": {
                            "status": "AVAILABLE",
                        },
                    },
                    "objective_context": {
                        "background_hr_median_bpm": {
                            "status": "NO_DATA",
                        },
                    },
                    "subjective": {
                        "fatigue_score": {
                            "status": "AVAILABLE",
                            "explicit": False,
                            "legacy_inferred": True,
                        },
                        "illness": {
                            "status": "NO_DATA",
                            "explicit": False,
                            "legacy_inferred": False,
                        },
                    },
                },
                "provenance": {},
            },
        },
    }

    facts = build_interpretation_facts(
        coach_inputs
    )

    assert facts == {
        "as_of_date": date(2026, 9, 30),
        "plan": {
            "planned_today_count": 1,
            "today_workouts": [
                {
                    "id": "workout-1",
                    "sport": "KAYAK",
                    "title": "8km kayaking",
                    "has_actual": False,
                    "link_source": None,
                },
            ],
            "active_periods": [
                {
                    "period_type": "MESOCYCLE",
                    "title": "Őszi alapozó ciklus 1",
                    "objectives": [
                        {
                            "objective_type": "ENDURANCE",
                            "weight": 0.6,
                        },
                        {
                            "objective_type": "STRENGTH",
                            "weight": 0.2,
                        },
                        {
                            "objective_type": "TECHNIQUE",
                            "weight": 0.2,
                        },
                    ],
                },
            ],
        },
        "athlete": {
            "load_available": True,
            "load_method": "NORMALIZED_EWMA",
            "acute_weekly_load": 151.53,
            "chronic_weekly_load": 110.09,
            "smoothed_acute_weekly_equivalent": 103.38,
            "smoothed_chronic_weekly_equivalent": 221.69,
            "readiness_available": True,
            "readiness_source": "MANUAL",
            "readiness_presence": {
                "objective": {
                    "hrv_rmssd_ms": {
                        "status": "AVAILABLE",
                    },
                },
                "objective_context": {
                    "background_hr_median_bpm": {
                        "status": "NO_DATA",
                    },
                },
                "subjective": {
                    "fatigue_score": {
                        "status": "AVAILABLE",
                        "explicit": False,
                        "legacy_inferred": True,
                    },
                    "illness": {
                        "status": "NO_DATA",
                        "explicit": False,
                        "legacy_inferred": False,
                    },
                },
            },
            "readiness_provenance": {},
            "readiness_values": {
                "objective": {
                    "hrv_rmssd_ms": 58.4,
                },
                "objective_context": {},
                "subjective": {
                    "fatigue_score": 4.0,
                },
            },
        },
    }


def test_build_descriptive_flags_remains_non_evaluative():
    facts = {
        "as_of_date": date(2026, 9, 30),
        "plan": {
            "planned_today_count": 1,
            "today_workouts": [
                {
                    "id": "workout-1",
                    "sport": "KAYAK",
                    "title": "8km kayaking",
                    "has_actual": False,
                    "link_source": None,
                },
            ],
        },
        "athlete": {
            "load_available": True,
            "acute_weekly_load": 151.53,
            "chronic_weekly_load": 110.09,
            "smoothed_acute_weekly_equivalent": 103.38,
            "smoothed_chronic_weekly_equivalent": 221.69,
            "readiness_available": True,
            "readiness_source": "MANUAL",
            "readiness_presence": {
                "objective": {
                    "hrv_rmssd_ms": {
                        "status": "AVAILABLE",
                    },
                    "sleep_score": {
                        "status": "AVAILABLE",
                    },
                },
                "objective_context": {},
                "subjective": {
                    "fatigue_score": {
                        "status": "AVAILABLE",
                    },
                    "illness": {
                        "status": "NO_DATA",
                    },
                    "travel": {
                        "status": "NO_DATA",
                    },
                },
            },
        },
    }

    flags = build_descriptive_flags(
        facts
    )

    assert flags == {
        "as_of_date": date(2026, 9, 30),
        "plan": {
            "has_planned_workout_today": True,
            "planned_today_count": 1,
            "with_actual_count": 0,
            "without_actual_count": 1,
        },
        "load": {
            "available": True,
            "raw_acute_vs_chronic": "ABOVE",
            "smoothed_acute_vs_chronic": "BELOW",
        },
        "readiness": {
            "available": True,
            "source": "MANUAL",
            "objective_available_metrics": [
                "hrv_rmssd_ms",
                "sleep_score",
            ],
            "subjective_available_metrics": [
                "fatigue_score",
            ],
            "illness_status": "NO_DATA",
            "travel_status": "NO_DATA",
        },
    }


def test_build_readiness_presence_summary_preserves_reporting_semantics():
    facts = {
        "athlete": {
            "readiness_available": True,
            "readiness_source": "MANUAL",
            "readiness_presence": {
                "objective": {
                    "hrv_rmssd_ms": {
                        "status": "AVAILABLE",
                    },
                    "sleep_score": {
                        "status": "AVAILABLE",
                    },
                },
                "objective_context": {
                    "background_hr_median_bpm": {
                        "status": "NO_DATA",
                    },
                },
                "subjective": {
                    "fatigue_score": {
                        "status": "AVAILABLE",
                        "explicit": False,
                        "legacy_inferred": True,
                    },
                    "energy_score": {
                        "status": "AVAILABLE",
                        "explicit": True,
                        "legacy_inferred": False,
                    },
                    "illness": {
                        "status": "NO_DATA",
                        "explicit": False,
                        "legacy_inferred": False,
                    },
                    "travel": {
                        "status": "NO_DATA",
                        "explicit": False,
                        "legacy_inferred": False,
                    },
                },
            },
        },
    }

    summary = (
        build_readiness_presence_summary(
            facts
        )
    )

    assert summary == {
        "available": True,
        "source": "MANUAL",
        "objective": {
            "available_metrics": [
                "hrv_rmssd_ms",
                "sleep_score",
            ],
            "no_data_metrics": [],
        },
        "objective_context": {
            "available_metrics": [],
            "no_data_metrics": [
                "background_hr_median_bpm",
            ],
        },
        "subjective": {
            "available_metrics": [
                "energy_score",
                "fatigue_score",
            ],
            "explicit_metrics": [
                "energy_score",
            ],
            "legacy_inferred_metrics": [
                "fatigue_score",
            ],
            "no_data_metrics": [
                "illness",
                "travel",
            ],
        },
    }


def test_build_readiness_provenance_summary_preserves_metric_sources():
    facts = {
        "athlete": {
            "readiness_source": (
                "PHYSIOLOGICAL_MEASUREMENTS"
            ),
            "readiness_provenance": {
                "hrv_rmssd_ms": {
                    "provider": "POLAR",
                    "measured_at": (
                        "2026-09-29T04:56:33"
                        ".006000+00:00"
                    ),
                    "measurement_id": (
                        "measurement-1"
                    ),
                    "source_record_id": (
                        "source-record-1"
                    ),
                    "availability": {
                        "schema_version": 1,
                        "total_observation_count": 1,
                        "metric_observation_count": 1,
                    },
                },
                "sleep_score": {
                    "provider": "POLAR",
                    "measured_at": (
                        "2026-09-29T03:50:17"
                        ".513000+00:00"
                    ),
                    "measurement_id": (
                        "measurement-2"
                    ),
                    "source_record_id": (
                        "source-record-2"
                    ),
                    "availability": {
                        "schema_version": 1,
                        "total_observation_count": 1,
                        "metric_observation_count": 1,
                    },
                },
            },
        },
    }

    summary = (
        build_readiness_provenance_summary(
            facts
        )
    )

    assert summary == {
        "readiness_source": (
            "PHYSIOLOGICAL_MEASUREMENTS"
        ),
        "metric_provenance_available": True,
        "metric_count": 2,
        "providers": [
            "POLAR",
        ],
        "metrics": {
            "hrv_rmssd_ms": {
                "provider": "POLAR",
                "measured_at": (
                    "2026-09-29T04:56:33"
                    ".006000+00:00"
                ),
                "measurement_id": (
                    "measurement-1"
                ),
                "source_record_id": (
                    "source-record-1"
                ),
                "availability": {
                    "schema_version": 1,
                    "total_observation_count": 1,
                    "metric_observation_count": 1,
                },
            },
            "sleep_score": {
                "provider": "POLAR",
                "measured_at": (
                    "2026-09-29T03:50:17"
                    ".513000+00:00"
                ),
                "measurement_id": (
                    "measurement-2"
                ),
                "source_record_id": (
                    "source-record-2"
                ),
                "availability": {
                    "schema_version": 1,
                    "total_observation_count": 1,
                    "metric_observation_count": 1,
                },
            },
        },
    }


def test_build_readiness_provenance_summary_handles_manual_without_metric_provenance():
    facts = {
        "athlete": {
            "readiness_source": "MANUAL",
            "readiness_provenance": {},
        },
    }

    summary = (
        build_readiness_provenance_summary(
            facts
        )
    )

    assert summary == {
        "readiness_source": "MANUAL",
        "metric_provenance_available": False,
        "metric_count": 0,
        "providers": [],
        "metrics": {},
    }


def test_build_readiness_coach_view_combines_values_presence_and_provenance():
    facts = {
        "athlete": {
            "readiness_available": True,
            "readiness_source": (
                "PHYSIOLOGICAL_MEASUREMENTS"
            ),
            "readiness_values": {
                "objective": {
                    "hrv_rmssd_ms": 44.0,
                },
                "objective_context": {},
                "subjective": {},
            },
            "readiness_presence": {
                "objective": {
                    "hrv_rmssd_ms": {
                        "status": "AVAILABLE",
                    },
                    "sleep_score": {
                        "status": "NO_DATA",
                    },
                },
                "objective_context": {
                    "background_hr_median_bpm": {
                        "status": "NO_DATA",
                    },
                },
                "subjective": {
                    "fatigue_score": {
                        "status": "NO_DATA",
                        "explicit": False,
                        "legacy_inferred": False,
                    },
                },
            },
            "readiness_provenance": {
                "hrv_rmssd_ms": {
                    "provider": "POLAR",
                    "measured_at": (
                        "2026-09-29T04:56:33"
                        ".006000+00:00"
                    ),
                    "measurement_id": (
                        "measurement-1"
                    ),
                    "source_record_id": (
                        "source-record-1"
                    ),
                    "availability": {
                        "schema_version": 1,
                        "total_observation_count": 1,
                        "metric_observation_count": 1,
                    },
                },
            },
        },
    }

    view = build_readiness_coach_view(
        facts
    )

    assert view["available"] is True

    assert (
        view["source"]
        == "PHYSIOLOGICAL_MEASUREMENTS"
    )

    assert view["values"] == {
        "objective": {
            "hrv_rmssd_ms": 44.0,
        },
        "objective_context": {},
        "subjective": {},
    }

    assert view["presence"]["objective"] == {
        "available_metrics": [
            "hrv_rmssd_ms",
        ],
        "no_data_metrics": [
            "sleep_score",
        ],
    }

    assert (
        view["provenance"][
            "metric_provenance_available"
        ]
        is True
    )

    assert view["provenance"][
        "providers"
    ] == [
        "POLAR",
    ]

    assert view["provenance"][
        "metric_count"
    ] == 1


def test_build_interpretation_signals_remains_non_prescriptive():
    facts = {
        "as_of_date": date(2026, 9, 30),
        "plan": {
            "active_periods": [
                {
                    "period_type": "MESOCYCLE",
                    "title": "Őszi alapozó ciklus 1",
                    "objectives": [
                        {
                            "objective_type": "ENDURANCE",
                            "weight": 0.6,
                        },
                        {
                            "objective_type": "STRENGTH",
                            "weight": 0.2,
                        },
                        {
                            "objective_type": "TECHNIQUE",
                            "weight": 0.2,
                        },
                    ],
                },
            ],
        },
    }

    flags = {
        "plan": {
            "planned_today_count": 1,
            "with_actual_count": 0,
            "without_actual_count": 1,
        },
        "load": {
            "raw_acute_vs_chronic": "ABOVE",
            "smoothed_acute_vs_chronic": "BELOW",
        },
        "readiness": {
            "illness_status": "NO_DATA",
            "travel_status": "NO_DATA",
        },
    }

    readiness_view = {
        "available": True,
        "source": "MANUAL",
        "presence": {
            "objective": {
                "available_metrics": [
                    "hrv_rmssd_ms",
                ],
                "no_data_metrics": [],
            },
            "objective_context": {
                "available_metrics": [],
                "no_data_metrics": [
                    "background_hr_median_bpm",
                ],
            },
            "subjective": {
                "available_metrics": [
                    "fatigue_score",
                ],
                "explicit_metrics": [],
                "legacy_inferred_metrics": [
                    "fatigue_score",
                ],
                "no_data_metrics": [
                    "illness",
                    "travel",
                ],
            },
        },
        "provenance": {
            "metric_provenance_available": False,
            "metric_count": 0,
            "providers": [],
            "metrics": {},
        },
    }

    result = build_interpretation_signals(
        interpretation_facts=facts,
        descriptive_flags=flags,
        readiness_coach_view=readiness_view,
    )

    assert result == {
        "as_of_date": date(2026, 9, 30),
        "signals": [
            {
                "code": "TODAY_WORKOUT_PENDING",
                "category": "PLAN",
                "evidence": {
                    "planned_today_count": 1,
                    "without_actual_count": 1,
                },
            },
            {
                "code": "LOAD_METHODS_DIVERGE",
                "category": "LOAD",
                "evidence": {
                    "raw_acute_vs_chronic": "ABOVE",
                    "smoothed_acute_vs_chronic": "BELOW",
                },
            },
            {
                "code": "ILLNESS_STATUS_UNKNOWN",
                "category": "READINESS",
                "evidence": {
                    "status": "NO_DATA",
                },
            },
            {
                "code": "TRAVEL_STATUS_UNKNOWN",
                "category": "READINESS",
                "evidence": {
                    "status": "NO_DATA",
                },
            },
            {
                "code": (
                    "READINESS_METRIC_PROVENANCE_UNAVAILABLE"
                ),
                "category": "EVIDENCE",
                "evidence": {
                    "readiness_source": "MANUAL",
                    "metric_count": 0,
                },
            },
            {
                "code": (
                    "SUBJECTIVE_VALUES_LEGACY_INFERRED"
                ),
                "category": "EVIDENCE",
                "evidence": {
                    "metrics": [
                        "fatigue_score",
                    ],
                },
            },
            {
                "code": (
                    "ACTIVE_PERIOD_DOMINANT_OBJECTIVE"
                ),
                "category": "PLAN",
                "evidence": {
                    "period_type": "MESOCYCLE",
                    "period_title": (
                        "Őszi alapozó ciklus 1"
                    ),
                    "objective_type": "ENDURANCE",
                    "weight": 0.6,
                },
            },
        ],
    }


def test_build_interpretation_signals_does_not_flag_available_metric_provenance():
    facts = {
        "as_of_date": date(2026, 9, 29),
        "plan": {
            "active_periods": [],
        },
    }

    flags = {
        "plan": {
            "planned_today_count": 0,
            "with_actual_count": 0,
            "without_actual_count": 0,
        },
        "load": {
            "raw_acute_vs_chronic": None,
            "smoothed_acute_vs_chronic": None,
        },
        "readiness": {
            "illness_status": None,
            "travel_status": None,
        },
    }

    readiness_view = {
        "available": True,
        "source": "PHYSIOLOGICAL_MEASUREMENTS",
        "presence": {
            "objective": {
                "available_metrics": [
                    "hrv_rmssd_ms",
                    "sleep_duration_sec",
                    "sleep_score",
                ],
                "no_data_metrics": [],
            },
            "objective_context": {
                "available_metrics": [],
                "no_data_metrics": [],
            },
            "subjective": {
                "available_metrics": [],
                "explicit_metrics": [],
                "legacy_inferred_metrics": [],
                "no_data_metrics": [],
            },
        },
        "provenance": {
            "metric_provenance_available": True,
            "metric_count": 3,
            "providers": [
                "POLAR",
            ],
            "metrics": {
                "hrv_rmssd_ms": {
                    "provider": "POLAR",
                },
                "sleep_duration_sec": {
                    "provider": "POLAR",
                },
                "sleep_score": {
                    "provider": "POLAR",
                },
            },
        },
    }

    result = build_interpretation_signals(
        interpretation_facts=facts,
        descriptive_flags=flags,
        readiness_coach_view=readiness_view,
    )

    codes = {
        item["code"]
        for item in result["signals"]
    }

    assert (
        "READINESS_METRIC_PROVENANCE_UNAVAILABLE"
        not in codes
    )

    assert (
        "SUBJECTIVE_VALUES_LEGACY_INFERRED"
        not in codes
    )


def test_build_coach_assessment_structures_signals_without_prescribing():
    signals = {
        "as_of_date": date(2026, 9, 30),
        "signals": [
            {
                "code": "TODAY_WORKOUT_PENDING",
                "category": "PLAN",
                "evidence": {
                    "planned_today_count": 1,
                    "without_actual_count": 1,
                },
            },
            {
                "code": "LOAD_METHODS_DIVERGE",
                "category": "LOAD",
                "evidence": {
                    "raw_acute_vs_chronic": "ABOVE",
                    "smoothed_acute_vs_chronic": "BELOW",
                },
            },
            {
                "code": "ILLNESS_STATUS_UNKNOWN",
                "category": "READINESS",
                "evidence": {
                    "status": "NO_DATA",
                },
            },
            {
                "code": "TRAVEL_STATUS_UNKNOWN",
                "category": "READINESS",
                "evidence": {
                    "status": "NO_DATA",
                },
            },
            {
                "code": (
                    "READINESS_METRIC_PROVENANCE_UNAVAILABLE"
                ),
                "category": "EVIDENCE",
                "evidence": {
                    "readiness_source": "MANUAL",
                    "metric_count": 0,
                },
            },
            {
                "code": (
                    "SUBJECTIVE_VALUES_LEGACY_INFERRED"
                ),
                "category": "EVIDENCE",
                "evidence": {
                    "metrics": [
                        "energy_score",
                        "fatigue_score",
                    ],
                },
            },
            {
                "code": (
                    "ACTIVE_PERIOD_DOMINANT_OBJECTIVE"
                ),
                "category": "PLAN",
                "evidence": {
                    "period_type": "MESOCYCLE",
                    "period_title": (
                        "Őszi alapozó ciklus 1"
                    ),
                    "objective_type": "ENDURANCE",
                    "weight": 0.6,
                },
            },
        ],
    }

    assessment = build_coach_assessment(
        signals
    )

    assert assessment == {
        "as_of_date": date(2026, 9, 30),
        "plan_execution": {
            "state": "PENDING_TODAY",
            "planned_today_count": 1,
            "without_actual_count": 1,
        },
        "load_pattern": {
            "state": "METHODS_DIVERGE",
            "raw_acute_vs_chronic": "ABOVE",
            "smoothed_acute_vs_chronic": "BELOW",
        },
        "readiness_evidence": {
            "gaps": [
                "ILLNESS_STATUS_UNKNOWN",
                "TRAVEL_STATUS_UNKNOWN",
            ],
            "metric_provenance_state": (
                "UNAVAILABLE"
            ),
            "legacy_inferred_subjective_metrics": [
                "energy_score",
                "fatigue_score",
            ],
        },
        "period_focus": {
            "period_type": "MESOCYCLE",
            "period_title": (
                "Őszi alapozó ciklus 1"
            ),
            "objective_type": "ENDURANCE",
            "weight": 0.6,
        },
        "signal_codes": [
            "TODAY_WORKOUT_PENDING",
            "LOAD_METHODS_DIVERGE",
            "ILLNESS_STATUS_UNKNOWN",
            "TRAVEL_STATUS_UNKNOWN",
            "READINESS_METRIC_PROVENANCE_UNAVAILABLE",
            "SUBJECTIVE_VALUES_LEGACY_INFERRED",
            "ACTIVE_PERIOD_DOMINANT_OBJECTIVE",
        ],
    }


def test_build_coach_assessment_does_not_infer_opposites_from_missing_signals():
    signals = {
        "as_of_date": date(2026, 9, 29),
        "signals": [],
    }

    assessment = build_coach_assessment(
        signals
    )

    assert assessment == {
        "as_of_date": date(2026, 9, 29),
        "plan_execution": None,
        "load_pattern": None,
        "readiness_evidence": {
            "gaps": [],
            "metric_provenance_state": None,
            "legacy_inferred_subjective_metrics": [],
        },
        "period_focus": None,
        "signal_codes": [],
    }