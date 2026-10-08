"""Preserve observed chronology without assigning physiological response lag."""

from collections import Counter
from collections.abc import Mapping
from itertools import pairwise
from typing import Any


def hr_response_temporal_policy() -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "target_domain": "RETROSPECTIVE_CONDITIONAL_RESPONSE",
        "hr_response": "DYNAMIC_DEPENDENT_ON_PRIOR_WORKLOAD_AND_RECOVERY",
        "hr_timestamps_preserved": True,
        "export_clock_offset_is_physiological_lag": False,
        "physiological_lag_ms": None,
        "fixed_hr_shift_applied": False,
        "history_horizon_ms": None,
        "history_horizon_status": "REQUIRES_INDIVIDUAL_MODEL_VALIDATION",
        "onset_and_recovery_parameters_shared": False,
        "physiological_state_reset_at_gap_verified": False,
        "missing_workload_or_hr_interpolated": False,
        "post_recording_recovery_extrapolated": False,
        "target_hr_used_as_predictor": False,
        "future_observed_workload_used_as_predictor": False,
        "causal_predictor_selection_status": "NOT_IMPLEMENTED",
        "current_segment_workload_for_causal_same_window_prediction": False,
        "observed_workload_availability": "SEGMENT_END_IS_A_LOWER_BOUND_PUBLICATION_TIME_NOT_VERIFIED",
        "pre_exercise_prediction_authorized": False,
        "split_grouping_unit": "ATHLETE_PROVIDER_SESSION",
        "split_assigned": False,
        "history_and_target_windows_must_share_split": True,
        "fatigue_relationship": "RESEARCH_HYPOTHESIS_REQUIRING_EXTERNAL_VALIDATION",
        "fatigue_score": None,
        "kinetics_estimator_configured": False,
        "training_authorized": False,
    }


def build_hr_response_temporal_context(
    windows: list[Mapping[str, Any]],
    input_segments: list[Mapping[str, Any]],
    *,
    duration_ms: Any,
    detail_limit: int = 25,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return source-order pointers into contiguous observed workload runs.

    These runs describe observation support, not physiological episodes or a
    verified reset of cardiovascular state. Missing HR does not erase workload
    history. A future estimator must select/validate its history horizon and
    treat left/right censoring explicitly. Never sort, shift or synthesize rows.
    """
    if type(detail_limit) is not int or not 1 <= detail_limit <= 100:
        raise ValueError("detail_limit must be an integer from 1 to 100")
    orders = [w.get("order_index") for w in windows]
    valid_orders = all(_index(o) for o in orders)
    unique_orders = valid_orders and len(set(orders)) == len(orders)
    reasons = []
    if not unique_orders:
        reasons.append("TEMPORAL_SEGMENT_IDENTITY_INVALID_OR_AMBIGUOUS")
    elif any(b <= a for a, b in pairwise(orders)):
        reasons.append("TEMPORAL_SEGMENTS_NOT_IN_SOURCE_ORDER")
    valid = [
        _index(w.get("start_exercise_elapsed_ms"))
        and _index(w.get("end_exercise_elapsed_ms"))
        and _index(duration_ms)
        and duration_ms > 0
        and w["start_exercise_elapsed_ms"] < w["end_exercise_elapsed_ms"] <= duration_ms
        for w in windows
    ]
    previous_end = None
    for w, usable in zip(windows, valid):
        if not usable:
            continue
        if previous_end is not None and w["start_exercise_elapsed_ms"] < previous_end:
            reasons.append("TEMPORAL_WINDOWS_OVERLAP_OR_REVERSE")
            break
        previous_end = w["end_exercise_elapsed_ms"]
    reasons = list(dict.fromkeys(reasons))
    inputs = {s.get("order_index"): s for s in input_segments if _index(s.get("order_index"))}
    input_counts = Counter(
        s.get("order_index") for s in input_segments if _index(s.get("order_index"))
    )
    contexts, runs = [], []
    current = None
    boundary_counts: Counter[str] = Counter()
    for position, (window, usable) in enumerate(zip(windows, valid)):
        order = window.get("order_index")
        item = inputs.get(order, {}) if _index(order) else {}
        workload = item.get("external_workload")
        workload = workload if isinstance(workload, Mapping) else {}
        supported = (
            usable
            and not reasons
            and _index(order)
            and input_counts[order] == 1
            and item.get("workload_available") is True
            and workload.get("start_exercise_elapsed_ms") == window.get("start_exercise_elapsed_ms")
            and workload.get("end_exercise_elapsed_ms") == window.get("end_exercise_elapsed_ms")
        )
        context = {
            "status": "OBSERVED_WORKLOAD_SEQUENCE" if supported else "WITHHELD",
            "sequence_index": None,
            "sequence_position": None,
            "history_start_order_index": None,
            "previous_order_index": None,
            "next_order_index": None,
            "history_includes_current_segment": False,
            "completed_history_end_order_index": None,
            "completed_history_end_exercise_elapsed_ms": None,
            "current_workload_available_not_before_exercise_elapsed_ms": None,
            "current_workload_role": "RETROSPECTIVE_CONDITIONING_ONLY",
            "hr_label_available_on_grid": window.get("grid_coverage_status") == "COMPLETE",
            "physiological_state_reset_verified": False,
        }
        contexts.append(context)
        if not supported:
            boundary_counts["INVALID_OR_UNSUPPORTED_WINDOW"] += 1
            current = None
            continue
        boundary = None
        if current is None:
            boundary = "OBSERVATION_START_OR_AFTER_UNSUPPORTED_WINDOW"
        elif orders[position - 1] + 1 != order:
            boundary = "SOURCE_ORDER_GAP"
        elif runs[-1]["end_exercise_elapsed_ms"] != window["start_exercise_elapsed_ms"]:
            boundary = "OBSERVED_TIME_GAP"
        elif workload.get("source_contiguous_with_previous") is False:
            boundary = "UPSTREAM_SOURCE_DISCONTINUITY"
        if boundary:
            boundary_counts[boundary] += 1
            current = len(runs)
            runs.append(
                {
                    "sequence_index": current,
                    "first_order_index": order,
                    "last_order_index": order,
                    "start_exercise_elapsed_ms": window["start_exercise_elapsed_ms"],
                    "end_exercise_elapsed_ms": window["end_exercise_elapsed_ms"],
                    "segment_count": 0,
                    "hr_label_segment_count": 0,
                    "left_boundary_reason": boundary,
                    "initial_physiological_state": "UNKNOWN",
                    "pre_observation_history_censored": True,
                    "post_observation_recovery_censored": True,
                }
            )
        run = runs[current]
        context.update(
            {
                "sequence_index": current,
                "sequence_position": run["segment_count"],
                "history_start_order_index": run["first_order_index"],
                "history_includes_current_segment": True,
                "current_workload_available_not_before_exercise_elapsed_ms": window[
                    "end_exercise_elapsed_ms"
                ],
            }
        )
        if run["segment_count"]:
            context["previous_order_index"] = orders[position - 1]
            context["completed_history_end_order_index"] = orders[position - 1]
            context["completed_history_end_exercise_elapsed_ms"] = window[
                "start_exercise_elapsed_ms"
            ]
            contexts[position - 1]["next_order_index"] = order
        run["segment_count"] += 1
        run["hr_label_segment_count"] += context["hr_label_available_on_grid"]
        run["last_order_index"] = order
        run["end_exercise_elapsed_ms"] = window["end_exercise_elapsed_ms"]
    summary = {
        "schema_version": "0.1",
        "status": "WITHHELD" if reasons else "OBSERVATION_SUPPORT_WITH_LIMITATIONS",
        "blocking_reasons": reasons,
        "sequence_count": len(runs),
        "supported_workload_segment_count": sum(r["segment_count"] for r in runs),
        "unsupported_window_count": sum(c["status"] == "WITHHELD" for c in contexts),
        "boundary_counts": dict(sorted(boundary_counts.items())),
        "sequences": {
            "total_count": len(runs),
            "returned_count": min(len(runs), detail_limit),
            "truncated": len(runs) > detail_limit,
            "items": runs[:detail_limit],
        },
        "policy": hr_response_temporal_policy(),
    }
    return contexts, summary


def _index(value: Any) -> bool:
    return type(value) is int and value >= 0
