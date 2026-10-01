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


def compare_optional_values(
    left: float | None,
    right: float | None,
) -> str | None:
    if left is None or right is None:
        return None

    if left > right:
        return "ABOVE"

    if left < right:
        return "BELOW"

    return "EQUAL"


def build_descriptive_flags(
    interpretation_facts: dict,
) -> dict:
    plan = interpretation_facts.get(
        "plan",
        {},
    )

    athlete = interpretation_facts.get(
        "athlete",
        {},
    )

    today_workouts = plan.get(
        "today_workouts",
        [],
    )

    readiness_presence = athlete.get(
        "readiness_presence",
        {},
    )

    objective_presence = (
        readiness_presence.get(
            "objective",
            {},
        )
    )

    subjective_presence = (
        readiness_presence.get(
            "subjective",
            {},
        )
    )

    return {
        "as_of_date": interpretation_facts.get(
            "as_of_date"
        ),
        "plan": {
            "has_planned_workout_today": (
                len(today_workouts) > 0
            ),
            "planned_today_count": len(
                today_workouts
            ),
            "with_actual_count": sum(
                1
                for workout in today_workouts
                if workout.get("has_actual")
                is True
            ),
            "without_actual_count": sum(
                1
                for workout in today_workouts
                if workout.get("has_actual")
                is not True
            ),
        },
        "load": {
            "available": athlete.get(
                "load_available",
                False,
            ),
            "raw_acute_vs_chronic": (
                compare_optional_values(
                    athlete.get(
                        "acute_weekly_load"
                    ),
                    athlete.get(
                        "chronic_weekly_load"
                    ),
                )
            ),
            "smoothed_acute_vs_chronic": (
                compare_optional_values(
                    athlete.get(
                        "smoothed_acute_weekly_equivalent"
                    ),
                    athlete.get(
                        "smoothed_chronic_weekly_equivalent"
                    ),
                )
            ),
        },
        "readiness": {
            "available": athlete.get(
                "readiness_available",
                False,
            ),
            "source": athlete.get(
                "readiness_source"
            ),
            "objective_available_metrics": sorted(
                key
                for key, presence
                in objective_presence.items()
                if (
                    presence.get("status")
                    == "AVAILABLE"
                )
            ),
            "subjective_available_metrics": sorted(
                key
                for key, presence
                in subjective_presence.items()
                if (
                    presence.get("status")
                    == "AVAILABLE"
                )
            ),
            "illness_status": (
                subjective_presence.get(
                    "illness",
                    {},
                ).get("status")
            ),
            "travel_status": (
                subjective_presence.get(
                    "travel",
                    {},
                ).get("status")
            ),
        },
    }


def build_readiness_presence_summary(
    interpretation_facts: dict,
) -> dict:
    athlete = interpretation_facts.get(
        "athlete",
        {},
    )

    presence = athlete.get(
        "readiness_presence",
        {},
    )

    objective = presence.get(
        "objective",
        {},
    )

    objective_context = presence.get(
        "objective_context",
        {},
    )

    subjective = presence.get(
        "subjective",
        {},
    )

    return {
        "available": athlete.get(
            "readiness_available",
            False,
        ),
        "source": athlete.get(
            "readiness_source"
        ),
        "objective": {
            "available_metrics": sorted(
                key
                for key, item in objective.items()
                if item.get("status")
                == "AVAILABLE"
            ),
            "no_data_metrics": sorted(
                key
                for key, item in objective.items()
                if item.get("status")
                == "NO_DATA"
            ),
        },
        "objective_context": {
            "available_metrics": sorted(
                key
                for key, item
                in objective_context.items()
                if item.get("status")
                == "AVAILABLE"
            ),
            "no_data_metrics": sorted(
                key
                for key, item
                in objective_context.items()
                if item.get("status")
                == "NO_DATA"
            ),
        },
        "subjective": {
            "available_metrics": sorted(
                key
                for key, item in subjective.items()
                if item.get("status")
                == "AVAILABLE"
            ),
            "explicit_metrics": sorted(
                key
                for key, item in subjective.items()
                if (
                    item.get("status")
                    == "AVAILABLE"
                    and item.get("explicit")
                    is True
                )
            ),
            "legacy_inferred_metrics": sorted(
                key
                for key, item in subjective.items()
                if (
                    item.get("status")
                    == "AVAILABLE"
                    and item.get(
                        "legacy_inferred"
                    )
                    is True
                )
            ),
            "no_data_metrics": sorted(
                key
                for key, item in subjective.items()
                if item.get("status")
                == "NO_DATA"
            ),
        },
    }


def build_readiness_provenance_summary(
    interpretation_facts: dict,
) -> dict:
    athlete = interpretation_facts.get(
        "athlete",
        {},
    )

    provenance = athlete.get(
        "readiness_provenance",
        {},
    ) or {}

    metrics = {}

    for metric_key, item in provenance.items():
        metrics[metric_key] = {
            "provider": item.get("provider"),
            "measured_at": item.get(
                "measured_at"
            ),
            "measurement_id": item.get(
                "measurement_id"
            ),
            "source_record_id": item.get(
                "source_record_id"
            ),
            "availability": item.get(
                "availability"
            ),
        }

    providers = sorted(
        {
            item["provider"]
            for item in metrics.values()
            if item["provider"] is not None
        }
    )

    return {
        "readiness_source": athlete.get(
            "readiness_source"
        ),
        "metric_provenance_available": (
            len(metrics) > 0
        ),
        "metric_count": len(metrics),
        "providers": providers,
        "metrics": metrics,
    }


def build_readiness_coach_view(
    interpretation_facts: dict,
) -> dict:
    athlete = interpretation_facts.get(
        "athlete",
        {},
    )

    presence_summary = (
        build_readiness_presence_summary(
            interpretation_facts
        )
    )

    provenance_summary = (
        build_readiness_provenance_summary(
            interpretation_facts
        )
    )

    return {
        "available": athlete.get(
            "readiness_available",
            False,
        ),
        "source": athlete.get(
            "readiness_source"
        ),
        "values": athlete.get(
            "readiness_values",
            {
                "objective": {},
                "objective_context": {},
                "subjective": {},
            },
        ),
        "presence": {
            "objective": presence_summary[
                "objective"
            ],
            "objective_context": (
                presence_summary[
                    "objective_context"
                ]
            ),
            "subjective": presence_summary[
                "subjective"
            ],
        },
        "provenance": {
            "metric_provenance_available": (
                provenance_summary[
                    "metric_provenance_available"
                ]
            ),
            "metric_count": (
                provenance_summary[
                    "metric_count"
                ]
            ),
            "providers": (
                provenance_summary[
                    "providers"
                ]
            ),
            "metrics": provenance_summary[
                "metrics"
            ],
        },
    }


def build_interpretation_signals(
    interpretation_facts: dict,
    descriptive_flags: dict,
    readiness_coach_view: dict,
) -> dict:
    signals: list[dict] = []

    plan_flags = descriptive_flags.get(
        "plan",
        {},
    )

    load_flags = descriptive_flags.get(
        "load",
        {},
    )

    readiness_flags = descriptive_flags.get(
        "readiness",
        {},
    )

    readiness_presence = (
        readiness_coach_view.get(
            "presence",
            {},
        )
    )

    readiness_provenance = (
        readiness_coach_view.get(
            "provenance",
            {},
        )
    )

    if (
        plan_flags.get(
            "without_actual_count",
            0,
        )
        > 0
    ):
        signals.append(
            {
                "code": "TODAY_WORKOUT_PENDING",
                "category": "PLAN",
                "evidence": {
                    "planned_today_count": (
                        plan_flags.get(
                            "planned_today_count",
                            0,
                        )
                    ),
                    "without_actual_count": (
                        plan_flags.get(
                            "without_actual_count",
                            0,
                        )
                    ),
                },
            }
        )

    raw_comparison = load_flags.get(
        "raw_acute_vs_chronic"
    )

    smoothed_comparison = load_flags.get(
        "smoothed_acute_vs_chronic"
    )

    if (
        raw_comparison is not None
        and smoothed_comparison is not None
        and raw_comparison
        != smoothed_comparison
    ):
        signals.append(
            {
                "code": "LOAD_METHODS_DIVERGE",
                "category": "LOAD",
                "evidence": {
                    "raw_acute_vs_chronic": (
                        raw_comparison
                    ),
                    "smoothed_acute_vs_chronic": (
                        smoothed_comparison
                    ),
                },
            }
        )

    if (
        readiness_flags.get(
            "illness_status"
        )
        == "NO_DATA"
    ):
        signals.append(
            {
                "code": "ILLNESS_STATUS_UNKNOWN",
                "category": "READINESS",
                "evidence": {
                    "status": "NO_DATA",
                },
            }
        )

    if (
        readiness_flags.get(
            "travel_status"
        )
        == "NO_DATA"
    ):
        signals.append(
            {
                "code": "TRAVEL_STATUS_UNKNOWN",
                "category": "READINESS",
                "evidence": {
                    "status": "NO_DATA",
                },
            }
        )

        if (
                readiness_coach_view.get(
                    "available",
                    False,
                )
                and readiness_provenance.get(
            "metric_provenance_available"
        )
                is False
        ):
            signals.append(
                {
                    "code": (
                        "READINESS_METRIC_PROVENANCE_UNAVAILABLE"
                    ),
                    "category": "EVIDENCE",
                    "evidence": {
                        "readiness_source": (
                            readiness_coach_view.get(
                                "source"
                            )
                        ),
                        "metric_count": (
                            readiness_provenance.get(
                                "metric_count",
                                0,
                            )
                        ),
                    },
                }
            )

        legacy_inferred_metrics = (
            readiness_presence.get(
                "subjective",
                {},
            ).get(
                "legacy_inferred_metrics",
                [],
            )
        )

        if legacy_inferred_metrics:
            signals.append(
                {
                    "code": (
                        "SUBJECTIVE_VALUES_LEGACY_INFERRED"
                    ),
                    "category": "EVIDENCE",
                    "evidence": {
                        "metrics": (
                            legacy_inferred_metrics
                        ),
                    },
                }
            )

    active_periods = (
        interpretation_facts.get(
            "plan",
            {},
        ).get(
            "active_periods",
            [],
        )
    )

    for period in active_periods:
        objectives = period.get(
            "objectives",
            [],
        )

        if not objectives:
            continue

        max_weight = max(
            objective.get(
                "weight",
                0.0,
            )
            for objective in objectives
        )

        dominant = [
            objective
            for objective in objectives
            if (
                objective.get(
                    "weight"
                )
                == max_weight
            )
        ]

        if len(dominant) != 1:
            continue

        objective = dominant[0]

        signals.append(
            {
                "code": (
                    "ACTIVE_PERIOD_DOMINANT_OBJECTIVE"
                ),
                "category": "PLAN",
                "evidence": {
                    "period_type": period.get(
                        "period_type"
                    ),
                    "period_title": period.get(
                        "title"
                    ),
                    "objective_type": (
                        objective.get(
                            "objective_type"
                        )
                    ),
                    "weight": objective.get(
                        "weight"
                    ),
                },
            }
        )

    return {
        "as_of_date": (
            interpretation_facts.get(
                "as_of_date"
            )
        ),
        "signals": signals,
    }


def build_coach_assessment(
    interpretation_signals: dict,
) -> dict:
    signals = interpretation_signals.get(
        "signals",
        [],
    )

    signals_by_code = {
        signal.get("code"): signal
        for signal in signals
        if signal.get("code") is not None
    }

    pending = signals_by_code.get(
        "TODAY_WORKOUT_PENDING"
    )

    load_divergence = signals_by_code.get(
        "LOAD_METHODS_DIVERGE"
    )

    provenance_missing = signals_by_code.get(
        "READINESS_METRIC_PROVENANCE_UNAVAILABLE"
    )

    legacy_subjective = signals_by_code.get(
        "SUBJECTIVE_VALUES_LEGACY_INFERRED"
    )

    dominant_objective = signals_by_code.get(
        "ACTIVE_PERIOD_DOMINANT_OBJECTIVE"
    )

    readiness_gaps = [
        code
        for code in (
            "ILLNESS_STATUS_UNKNOWN",
            "TRAVEL_STATUS_UNKNOWN",
        )
        if code in signals_by_code
    ]

    return {
        "as_of_date": interpretation_signals.get(
            "as_of_date"
        ),
        "plan_execution": (
            {
                "state": "PENDING_TODAY",
                "planned_today_count": (
                    pending.get(
                        "evidence",
                        {},
                    ).get(
                        "planned_today_count"
                    )
                ),
                "without_actual_count": (
                    pending.get(
                        "evidence",
                        {},
                    ).get(
                        "without_actual_count"
                    )
                ),
            }
            if pending is not None
            else None
        ),
        "load_pattern": (
            {
                "state": "METHODS_DIVERGE",
                "raw_acute_vs_chronic": (
                    load_divergence.get(
                        "evidence",
                        {},
                    ).get(
                        "raw_acute_vs_chronic"
                    )
                ),
                "smoothed_acute_vs_chronic": (
                    load_divergence.get(
                        "evidence",
                        {},
                    ).get(
                        "smoothed_acute_vs_chronic"
                    )
                ),
            }
            if load_divergence is not None
            else None
        ),
        "readiness_evidence": {
            "gaps": readiness_gaps,
            "metric_provenance_state": (
                "UNAVAILABLE"
                if provenance_missing is not None
                else None
            ),
            "legacy_inferred_subjective_metrics": (
                legacy_subjective.get(
                    "evidence",
                    {},
                ).get(
                    "metrics",
                    [],
                )
                if legacy_subjective is not None
                else []
            ),
        },
        "period_focus": (
            {
                "period_type": (
                    dominant_objective.get(
                        "evidence",
                        {},
                    ).get(
                        "period_type"
                    )
                ),
                "period_title": (
                    dominant_objective.get(
                        "evidence",
                        {},
                    ).get(
                        "period_title"
                    )
                ),
                "objective_type": (
                    dominant_objective.get(
                        "evidence",
                        {},
                    ).get(
                        "objective_type"
                    )
                ),
                "weight": (
                    dominant_objective.get(
                        "evidence",
                        {},
                    ).get(
                        "weight"
                    )
                ),
            }
            if dominant_objective is not None
            else None
        ),
        "signal_codes": [
            signal.get("code")
            for signal in signals
            if signal.get("code") is not None
        ],
    }


def build_coach_state(
    coach_assessment: dict,
    readiness_coach_view: dict,
    interpretation_facts: dict,
) -> dict:
    plan_facts = interpretation_facts.get(
        "plan",
        {},
    )

    return {
        "as_of_date": coach_assessment.get(
            "as_of_date"
        ),
        "plan": {
            "execution": coach_assessment.get(
                "plan_execution"
            ),
            "period_focus": coach_assessment.get(
                "period_focus"
            ),
            "today_workouts": plan_facts.get(
                "today_workouts",
                [],
            ),
        },
        "load": {
            "pattern": coach_assessment.get(
                "load_pattern"
            ),
        },
        "readiness": {
            "evidence": coach_assessment.get(
                "readiness_evidence"
            ),
            "view": readiness_coach_view,
        },
        "signal_codes": coach_assessment.get(
            "signal_codes",
            [],
        ),
    }