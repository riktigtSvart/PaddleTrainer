from datetime import date

from app.services.coach_context import (
    build_coach_context,
    build_coach_inputs,
    build_interpretation_facts,
    build_today_plan,
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