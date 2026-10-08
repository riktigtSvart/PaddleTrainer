from copy import deepcopy

import pytest

from app.services.hr_response_temporal_context import build_hr_response_temporal_context


def series(bounds, *, orders=None, coverage=None):
    orders = list(range(len(bounds))) if orders is None else orders
    coverage = ["COMPLETE"] * len(bounds) if coverage is None else coverage
    windows = [
        {
            "order_index": o,
            "start_exercise_elapsed_ms": a,
            "end_exercise_elapsed_ms": b,
            "grid_coverage_status": c,
        }
        for o, (a, b), c in zip(orders, bounds, coverage)
    ]
    inputs = [
        {
            "order_index": w["order_index"],
            "workload_available": True,
            "external_workload": {k: v for k, v in w.items() if k != "grid_coverage_status"},
        }
        for w in windows
    ]
    return windows, inputs


def test_history_is_preserved_during_delayed_hr_response_and_unlabelled_tail():
    windows, inputs = series(
        [(0, 1000), (1000, 2000), (2000, 3000), (3000, 4000)],
        coverage=["COMPLETE", "COMPLETE", "NO_SAMPLES", "NO_SAMPLES"],
    )
    # Pulse of observed ground motion followed by cessation: never move HR rows
    # or declare that ground speed itself is measured physiological workload.
    for item, speed in zip(inputs, [2, 4, 1, 0]):
        item["external_workload"]["gps_ground_speed_mps"] = speed
    original = deepcopy((windows, inputs))
    contexts, summary = build_hr_response_temporal_context(windows, inputs, duration_ms=4000)
    assert (windows, inputs) == original
    assert summary["sequence_count"] == 1
    assert summary["supported_workload_segment_count"] == 4
    assert summary["sequences"]["items"][0]["hr_label_segment_count"] == 2
    assert [c["previous_order_index"] for c in contexts] == [None, 0, 1, 2]
    assert [c["next_order_index"] for c in contexts] == [1, 2, 3, None]
    assert all(c["history_start_order_index"] == 0 for c in contexts)
    assert [c["completed_history_end_order_index"] for c in contexts] == [None, 0, 1, 2]
    assert [c["current_workload_available_not_before_exercise_elapsed_ms"] for c in contexts] == [
        1000,
        2000,
        3000,
        4000,
    ]
    assert contexts[2]["completed_history_end_exercise_elapsed_ms"] == 2000
    assert contexts[-1]["hr_label_available_on_grid"] is False
    policy = summary["policy"]
    assert policy["hr_timestamps_preserved"] is True
    assert policy["fixed_hr_shift_applied"] is False
    assert policy["physiological_lag_ms"] is None
    assert policy["history_horizon_ms"] is None
    assert policy["export_clock_offset_is_physiological_lag"] is False
    assert policy["target_hr_used_as_predictor"] is False
    assert policy["future_observed_workload_used_as_predictor"] is False
    assert policy["current_segment_workload_for_causal_same_window_prediction"] is False
    assert policy["fatigue_score"] is None
    assert policy["training_authorized"] is False


@pytest.mark.parametrize("boundary", ["TIME_GAP", "ORDER_GAP", "SOURCE_DISCONTINUITY"])
def test_unknown_continuity_starts_a_new_observation_run_without_claiming_recovery(boundary):
    windows, inputs = series([(0, 1000), (1000, 2000), (2000, 3000)])
    if boundary == "TIME_GAP":
        windows[1]["start_exercise_elapsed_ms"] = 1500
        inputs[1]["external_workload"]["start_exercise_elapsed_ms"] = 1500
    elif boundary == "ORDER_GAP":
        for w, s, o in zip(windows, inputs, [0, 2, 3]):
            w["order_index"] = s["order_index"] = o
    else:
        inputs[1]["external_workload"]["source_contiguous_with_previous"] = False
    contexts, summary = build_hr_response_temporal_context(windows, inputs, duration_ms=3000)
    assert summary["sequence_count"] == 2
    assert contexts[0]["next_order_index"] is None
    assert contexts[1]["previous_order_index"] is None
    assert contexts[2]["history_start_order_index"] == windows[1]["order_index"]
    assert all(r["initial_physiological_state"] == "UNKNOWN" for r in summary["sequences"]["items"])
    assert all(c["physiological_state_reset_verified"] is False for c in contexts)


@pytest.mark.parametrize("orders", [[0, 0], [1, 0], [False, 1], [-1, 1], [0.0, 1], [None, 1]])
def test_ambiguous_or_reordered_source_never_gets_history_pointers(orders):
    windows, inputs = series([(0, 1000), (1000, 2000)], orders=orders)
    contexts, summary = build_hr_response_temporal_context(windows, inputs, duration_ms=2000)
    assert summary["status"] == "WITHHELD"
    assert summary["blocking_reasons"]
    assert summary["sequence_count"] == 0
    assert all(c["sequence_index"] is None for c in contexts)


@pytest.mark.parametrize(
    "bounds",
    [[(0, 1100), (1000, 2000)], [(1000, 2000), (0, 1000)], [(0, 3000), (1000, 2000), (2000, 2500)]],
)
def test_overlapping_windows_block_the_whole_temporal_sequence(bounds):
    windows, inputs = series(bounds)
    contexts, summary = build_hr_response_temporal_context(windows, inputs, duration_ms=3000)
    assert summary["blocking_reasons"] == ["TEMPORAL_WINDOWS_OVERLAP_OR_REVERSE"]
    assert all(c["status"] == "WITHHELD" for c in contexts)


@pytest.mark.parametrize(
    "bad_bounds",
    [
        (-1, 2000),
        (1000, 1000),
        (1000, 999),
        (1000, 4001),
        (False, 2000),
        (1000.0, 2000),
        (1000, None),
    ],
)
def test_invalid_window_is_excluded_without_bridging_its_history(bad_bounds):
    windows, inputs = series([(0, 1000), bad_bounds, (2000, 3000)])
    contexts, summary = build_hr_response_temporal_context(windows, inputs, duration_ms=4000)
    assert summary["sequence_count"] == 2
    assert summary["unsupported_window_count"] == 1
    assert contexts[1]["status"] == "WITHHELD"
    assert contexts[0]["next_order_index"] is None
    assert contexts[2]["previous_order_index"] is None


@pytest.mark.parametrize("failure", ["MISSING", "DUPLICATE", "WINDOW_MISMATCH", "UNAVAILABLE"])
def test_workload_identity_and_window_support_are_required(failure):
    windows, inputs = series([(0, 1000), (1000, 2000), (2000, 3000)])
    if failure == "MISSING":
        inputs.pop(1)
    elif failure == "DUPLICATE":
        inputs.append(deepcopy(inputs[1]))
    elif failure == "WINDOW_MISMATCH":
        inputs[1]["external_workload"]["end_exercise_elapsed_ms"] += 1
    else:
        inputs[1]["workload_available"] = False
    contexts, summary = build_hr_response_temporal_context(windows, inputs, duration_ms=3000)
    assert contexts[1]["status"] == "WITHHELD"
    assert summary["sequence_count"] == 2


def test_bounded_run_packet_keeps_complete_counts():
    windows, inputs = series([(i * 2000, i * 2000 + 1000) for i in range(120)])
    contexts, summary = build_hr_response_temporal_context(windows, inputs, duration_ms=240000)
    packet = summary["sequences"]
    assert len(contexts) == packet["total_count"] == 120
    assert packet["returned_count"] == 25
    assert packet["truncated"] is True


@pytest.mark.parametrize("limit", [0, 101, True, 1.0, None])
def test_invalid_detail_limit_rejected(limit):
    with pytest.raises(ValueError):
        build_hr_response_temporal_context([], [], duration_ms=1, detail_limit=limit)


def test_empty_observation_has_no_supported_sequences():
    contexts, summary = build_hr_response_temporal_context([], [], duration_ms=1000)
    assert contexts == []
    assert summary["sequence_count"] == 0
