from datetime import date


def build_today_plan(
    plan_context: dict,
    as_of_date: date,
) -> dict:
    current_week = plan_context.get(
        "current_week",
        {},
    )

    planned_workouts = current_week.get(
        "planned_workouts",
        [],
    )

    todays_workouts = [
        workout
        for workout in planned_workouts
        if workout.get("date") == as_of_date
    ]

    return {
        "date": as_of_date,
        "planned_workouts": todays_workouts,
    }


def build_coach_context(
    athlete_state: dict,
    as_of_date: date,
) -> dict:
    plan_context = athlete_state.get(
        "plan_context",
        {},
    )

    today_plan = build_today_plan(
        plan_context=plan_context,
        as_of_date=as_of_date,
    )

    return {
        "as_of_date": as_of_date,
        "athlete_state": athlete_state,
        "today_plan": today_plan,
    }


def build_coach_inputs(
    coach_context: dict,
) -> dict:
    athlete_state = coach_context.get(
        "athlete_state",
        {},
    )

    plan_context = athlete_state.get(
        "plan_context",
        {},
    )

    return {
        "as_of_date": coach_context.get(
            "as_of_date"
        ),
        "plan": {
            "today": coach_context.get(
                "today_plan"
            ),
            "active_periods": (
                plan_context.get(
                    "active_periods",
                    [],
                )
            ),
        },
        "athlete": {
            "training_load": (
                athlete_state.get(
                    "training_load"
                )
            ),
            "readiness": athlete_state.get(
                "readiness"
            ),
            "capacity_evidence": (
                athlete_state.get(
                    "capacity_evidence"
                )
            ),
            "long_term_background_evidence": (
                athlete_state.get(
                    "long_term_background_evidence"
                )
            ),
            "response_trajectories": (
                athlete_state.get(
                    "response_trajectories"
                )
            ),
        },
    }


def filter_available_values(
    values: dict,
    presence: dict,
) -> dict:
    return {
        key: value
        for key, value in values.items()
        if (
            presence.get(
                key,
                {},
            ).get("status")
            == "AVAILABLE"
        )
    }


def build_interpretation_facts(
    coach_inputs: dict,
) -> dict:
    plan = coach_inputs.get(
        "plan",
        {},
    )

    athlete = coach_inputs.get(
        "athlete",
        {},
    )

    today = plan.get(
        "today",
        {},
    ) or {}

    today_workouts = today.get(
        "planned_workouts",
        [],
    )

    active_periods = plan.get(
        "active_periods",
        [],
    )

    readiness = athlete.get(
        "readiness"
    )

    training_load = athlete.get(
        "training_load"
    )

    smoothed_load = (
        training_load.get(
            "smoothed",
            {},
        )
        if training_load is not None
        else {}
    )

    readiness_presence = (
        readiness.get(
            "presence",
            {},
        )
        if readiness is not None
        else {}
    )

    readiness_objective = (
        readiness.get(
            "objective",
            {},
        )
        if readiness is not None
        else {}
    )

    readiness_objective_context = (
        readiness.get(
            "objective_context",
            {},
        )
        if readiness is not None
        else {}
    )

    readiness_subjective = (
        readiness.get(
            "subjective",
            {},
        )
        if readiness is not None
        else {}
    )

    return {
        "as_of_date": coach_inputs.get(
            "as_of_date"
        ),
        "plan": {
            "planned_today_count": len(
                today_workouts
            ),
            "today_workouts": [
                {
                    "id": workout.get("id"),
                    "sport": workout.get("sport"),
                    "title": workout.get("title"),
                    "has_actual": (
                        workout.get(
                            "execution",
                            {},
                        ).get(
                            "has_actual",
                            False,
                        )
                    ),
                    "link_source": (
                        workout.get(
                            "execution",
                            {},
                        ).get(
                            "link_source"
                        )
                    ),
                }
                for workout in today_workouts
            ],
            "active_periods": [
                {
                    "period_type": period.get(
                        "period_type"
                    ),
                    "title": period.get(
                        "title"
                    ),
                    "objectives": [
                        {
                            "objective_type": (
                                objective.get(
                                    "objective_type"
                                )
                            ),
                            "weight": objective.get(
                                "weight"
                            ),
                        }
                        for objective in period.get(
                            "objectives",
                            [],
                        )
                    ],
                }
                for period in active_periods
            ],
        },
        "athlete": {
            "load_available": (
                    training_load is not None
            ),
            "load_method": (
                smoothed_load.get("method")
            ),
            "acute_weekly_load": (
                training_load.get(
                    "acute",
                    {},
                ).get("weekly_load")
                if training_load is not None
                else None
            ),
            "chronic_weekly_load": (
                training_load.get(
                    "chronic",
                    {},
                ).get("weekly_load")
                if training_load is not None
                else None
            ),
            "smoothed_acute_weekly_equivalent": (
                smoothed_load.get(
                    "acute",
                    {},
                ).get(
                    "weekly_equivalent"
                )
            ),
            "smoothed_chronic_weekly_equivalent": (
                smoothed_load.get(
                    "chronic",
                    {},
                ).get(
                    "weekly_equivalent"
                )
            ),
            "readiness_available": (
                    readiness is not None
            ),
            "readiness_source": (
                readiness.get("source")
                if readiness is not None
                else None
            ),
            "readiness_presence": {
                "objective": (
                    readiness_presence.get(
                        "objective",
                        {},
                    )
                ),
                "objective_context": (
                    readiness_presence.get(
                        "objective_context",
                        {},
                    )
                ),
                "subjective": (
                    readiness_presence.get(
                        "subjective",
                        {},
                    )
                ),
            },
            "readiness_values": {
                "objective": filter_available_values(
                    readiness_objective,
                    readiness_presence.get(
                        "objective",
                        {},
                    ),
                ),
                "objective_context": (
                    filter_available_values(
                        readiness_objective_context,
                        readiness_presence.get(
                            "objective_context",
                            {},
                        ),
                    )
                ),
                "subjective": filter_available_values(
                    readiness_subjective,
                    readiness_presence.get(
                        "subjective",
                        {},
                    ),
                ),
            },
            "readiness_provenance": (
                readiness.get(
                    "provenance",
                    {},
                )
                if readiness is not None
                else {}
            ),
        },
    }