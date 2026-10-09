from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from test_environment_replay_persistence import scientific_state
from test_response_experiment_contract import (
    archive as _archive,
    chronological as _chronological,
    completed as _completed,
    environment as _environment,
    sources as _sources,
)

from app.schemas.response_cohort import ResponseCohortManifest
from app.services import response_model_inputs as module
from app.services.environment_replay_snapshot import canonical_hash
from app.services.response_cohort_storage_contract import build_cohort_record_payload
from app.services.response_dataset_integrity import check_response_dataset_integrity
from app.services.response_experiment_contract import build_response_experiment_manifest

archive, completed, chronological, environment, sources = (
    _archive,
    _completed,
    _chronological,
    _environment,
    _sources,
)


@pytest.fixture
def inputs(archive, completed):
    env, _ = completed
    return archive, deepcopy(env.packages)


def plan(archive, windows=None, environment=None):
    return build_response_experiment_manifest(
        archive,
        experiment_id="interval-input-tests",
        lookback_windows_ms=[1000, 3000] if windows is None else windows,
        environment_features=environment,
    )


def rehash(value):
    value["input_package_hash"] = canonical_hash(
        {k: v for k, v in value.items() if k != "input_package_hash"}
    )
    return value


def repin_local_fixture(record, datasets):
    """Update synthetic local commitments, never pretend to revalidate a source."""
    request, index = deepcopy(record["request_manifest"]), deepcopy(record["cohort_index"])
    for dataset in datasets:
        dataset["package_hash"] = canonical_hash(
            {k: v for k, v in dataset.items() if k != "package_hash"}
        )
        integrity = check_response_dataset_integrity(dataset)
        sid = dataset["session_external_id"]
        member = next(m for m in index["members"] if m["session_external_id"] == sid)
        pin = next(m for m in request["members"] if m["session_external_id"] == sid)
        member["unassigned_replay_package_hash"] = pin[
            "expected_unassigned_replay_package_hash"
        ] = dataset["package_hash"]
        member["counts"] = {k: dataset[k] for k in member["counts"]}
        member["feature_status_counts"] = deepcopy(dataset["feature_status_counts"])
        member["hr_window_status_counts"] = integrity["hr_window_status_counts"]
        seqs = [s for r in dataset["routes"] for s in r["sequences"]]
        member["history_summary"] = {
            "sequence_count": len(seqs),
            "supported_workload_observation_count": sum(
                r["supported_workload_observation_count"] for r in dataset["routes"]
            ),
            "unknown_initial_state_sequence_count": len(seqs),
            "pre_observation_censored_sequence_count": len(seqs),
            "post_observation_censored_sequence_count": len(seqs),
        }
    index["totals"] = {k: sum(m["counts"][k] for m in index["members"]) for k in index["totals"]}
    index["request_manifest_hash"] = ResponseCohortManifest.model_validate(
        request
    ).request_manifest_hash()
    index["cohort_index_hash"] = canonical_hash(
        {k: v for k, v in index.items() if k != "cohort_index_hash"}
    )
    return build_cohort_record_payload(request, index, owner_id=record["owner_id"])


def masked_fixture(inputs, mask, row_index=0):
    record, datasets = deepcopy(inputs)
    for dataset in datasets:
        features = dataset["observations"][row_index]["environment_features"]
        features["headwind_component_mps"].update(status=mask, available=False, value=None)
        dataset["feature_status_counts"]["headwind_component_mps"] = dict(
            Counter(
                r["environment_features"]["headwind_component_mps"]["status"]
                for r in dataset["observations"]
            )
        )
    return repin_local_fixture(record, datasets), datasets


def test_actual_assembler_fixture_binds_arrays_means_clipped_history_and_split_without_calls(
    inputs, completed
):
    record, datasets = inputs
    env, _ = completed
    original = deepcopy(inputs)
    before, calls, commits = scientific_state(env), env.provider.await_count, env.db.commit_count
    contract = plan(record)
    package = module.build_response_model_input_package(contract, record, datasets)
    assert package == module.build_response_model_input_package(
        contract, record, list(reversed(datasets))
    )
    checked = module.check_response_model_input_package(package, contract, record, datasets)
    assert (
        checked["model_input_arrays_checked"]
        is checked["row_level_history_coverage_verified"]
        is True
    )
    assert checked["model_input_row_count"] == 3
    assert checked["source_observation_count"] == 6
    assert checked["excluded_observation_count"] == 3
    assert package["per_split_coverage"]["TRAIN"]["model_input_row_count"] == 1
    assert [m["session_external_id"] for m in package["members"]] == [
        "session-1",
        "session-2",
        "session-3",
    ]
    assert [m["split"] for m in package["members"]] == ["TRAIN", "TEST", "VALIDATION"]
    for member in package["members"]:
        dataset = next(
            d for d in datasets if d["session_external_id"] == member["session_external_id"]
        )
        target = member["targets"][0]
        assert target["input_row_index"] == 1
        assert (
            target["recorded_hr_mean_bpm"]
            == sum(s["value_bpm"] for s in dataset["hr_streams"][0]["samples"][2:4]) / 2
        )
        short, long = target["history_windows"]
        assert short["first_input_row_index_inclusive"] == 1
        assert short["first_interval_clip_ms"] == 1000
        assert long["first_input_row_index_inclusive"] == 0
        assert long["first_interval_clip_ms"] == 1000
        assert long["stop_input_row_index_exclusive"] == 2
        assert member["row_audit"][0]["exclusion_reasons"] == ["LEFT_CENSORED_HISTORY"]
        assert member["sequence_metadata"][0]["initial_physiological_state"] == "UNKNOWN"
        assert dataset["split_assignment"]["split"] is None
    for key in (
        "source_evidence_verified",
        "current_source_evidence_verified",
        "owner_authorization_verified",
        "database_record_persisted",
        "split_assignment_persisted",
        "training_authorized",
        "numeric_output_authorized",
        "model_fit_performed",
        "fitted_preprocessing_performed",
    ):
        assert checked[key] is False
    assert inputs == original and scientific_state(env) == before
    assert env.provider.await_count == calls and env.db.commit_count == commits


@pytest.mark.parametrize("width,expected", [(1999, 6), (2000, 6), (2001, 3), (4000, 3), (4001, 0)])
def test_exact_history_boundary_is_half_open_and_longest_required_window_controls_rows(
    inputs, width, expected
):
    record, datasets = inputs
    package = module.build_response_model_input_package(plan(record, [width]), record, datasets)
    assert package["totals"]["model_input_row_count"] == expected
    for member in package["members"]:
        for target in member["targets"]:
            ref = target["history_windows"][0]
            assert ref["covered_duration_ms"] == width
            assert ref["stop_exercise_elapsed_ms"] - ref["start_exercise_elapsed_ms"] == width


def test_missing_hr_label_still_supplies_workload_to_later_valid_target(inputs):
    record, datasets = deepcopy(inputs)
    for dataset in datasets:
        stream = dataset["hr_streams"][0]
        stream["samples"][0].update(value_bpm=None, positive_finite=False)
        stream["positive_finite_sample_count"] -= 1
        row = dataset["observations"][0]
        row["hr_label_ref"].update(
            status="PARTIAL",
            positive_finite_grid_sample_count=1,
            missing_or_invalid_grid_slot_count=1,
        )
        row.update(preparation_candidate=False, exclusion_reasons=["HR_LABEL_GRID_INCOMPLETE"])
        dataset.update(
            preparation_candidate_count=1, excluded_observation_count=1, complete_hr_window_count=1
        )
        dataset["routes"][0].update(preparation_candidate_count=1, complete_hr_window_count=1)
    record = repin_local_fixture(record, datasets)
    package = module.build_response_model_input_package(plan(record, [3000]), record, datasets)
    assert package["totals"]["model_input_row_count"] == 3
    for member in package["members"]:
        assert member["row_audit"][0]["source_preparation_candidate"] is False
        assert member["targets"][0]["history_windows"][0]["first_input_row_index_inclusive"] == 0
        assert member["input_arrays"]["values"][0][0] == 2.5


@pytest.mark.parametrize("mask", ["MISSING", "WITHHELD", "NOT_APPLICABLE"])
def test_each_unavailable_mask_is_preserved_and_disqualifies_overlapping_history(inputs, mask):
    record, datasets = masked_fixture(inputs, mask)
    package = module.build_response_model_input_package(plan(record, [3000]), record, datasets)
    assert package["totals"]["model_input_row_count"] == 0
    headwind = next(
        i for i, c in enumerate(package["columns"]) if c["name"] == "headwind_component_mps"
    )
    for member in package["members"]:
        assert member["input_arrays"]["masks"][0][headwind] == mask
        assert member["input_arrays"]["values"][0][headwind] is None
        check = member["row_audit"][1]["history_checks"][0]
        assert check["status"] == "SELECTED_INPUT_MASKED"
        assert check["unavailable_features"] == ["headwind_component_mps"]


def test_future_masked_interval_does_not_affect_earlier_target(inputs):
    record, datasets = masked_fixture(inputs, "WITHHELD", row_index=1)
    package = module.build_response_model_input_package(plan(record, [1000]), record, datasets)
    for member in package["members"]:
        assert [t["input_row_index"] for t in member["targets"]] == [0]
        assert member["targets"][0]["history_windows"][0]["stop_input_row_index_exclusive"] == 1


def test_unselected_withheld_feature_does_not_exclude_motion_only_input(inputs):
    record, datasets = masked_fixture(inputs, "WITHHELD")
    package = module.build_response_model_input_package(plan(record, [3000], []), record, datasets)
    assert [c["name"] for c in package["columns"]] == ["gps_ground_speed_mps"]
    assert package["totals"]["model_input_row_count"] == 3


def test_default_windows_produce_diagnosed_empty_partitions_for_short_fixture_without_padding(
    inputs,
):
    record, datasets = inputs
    contract = build_response_experiment_manifest(record, experiment_id="too-short")
    package = module.build_response_model_input_package(contract, record, datasets)
    assert package["status"] == "MODEL_INPUT_PACKAGE_WITH_EMPTY_PARTITIONS"
    assert package["empty_input_partitions"] == ["TRAIN", "VALIDATION", "TEST"]
    assert package["totals"]["excluded_observation_count"] == 6
    assert package["policy"]["missing_values_imputed"] is False


def test_real_gap_is_a_new_left_censored_sequence_not_a_physiological_reset(inputs):
    record, datasets = deepcopy(inputs)
    for dataset in datasets:
        first, second = dataset["observations"]
        first["end_exercise_elapsed_ms"] = 1000
        first["workload_observation"].update(end_exercise_elapsed_ms=1000, interval_ms=1000)
        first["temporal_context"]["current_workload_available_not_before_exercise_elapsed_ms"] = (
            1000
        )
        first["hr_label_ref"].update(
            grid_stop_index_exclusive=1,
            recorded_slot_count=1,
            expected_grid_slot_count=1,
            positive_finite_grid_sample_count=1,
        )
        second["history_ref"].update(
            sequence_index=1, first_order_index=1, completed_end_order_index=None
        )
        second["temporal_context"].update(
            sequence_index=1,
            sequence_position=0,
            history_start_order_index=1,
            completed_history_end_order_index=None,
        )
        route = dataset["routes"][0]
        old = route["sequences"][0]
        route["sequence_count"] = 2
        route["sequences"] = [
            {**old, "last_order_index": 0, "observation_count": 1, "end_exercise_elapsed_ms": 1000},
            {
                **old,
                "sequence_index": 1,
                "first_order_index": 1,
                "observation_count": 1,
                "start_exercise_elapsed_ms": 2000,
            },
        ]
    record = repin_local_fixture(record, datasets)
    package = module.build_response_model_input_package(plan(record, [3000]), record, datasets)
    assert package["totals"]["model_input_row_count"] == 0
    for member in package["members"]:
        assert len(member["sequence_metadata"]) == 2
        assert member["row_audit"][1]["history_checks"][0]["status"] == "LEFT_CENSORED_HISTORY"
        assert all(s["physiological_reset_verified"] is False for s in member["sequence_metadata"])


@pytest.mark.parametrize(
    "case",
    [
        "value",
        "mask",
        "target",
        "future",
        "cross_member",
        "split",
        "extra_hr",
        "authority",
        "bool_alias",
        "drop_audit",
    ],
)
def test_valid_recomputed_hash_cannot_hide_array_history_label_or_authority_changes(inputs, case):
    record, datasets = inputs
    contract = plan(record)
    package = module.build_response_model_input_package(contract, record, datasets)
    member = package["members"][0]
    if case == "value":
        member["input_arrays"]["values"][0][0] += 1
    elif case == "mask":
        member["input_arrays"]["masks"][0][0] = "WITHHELD"
    elif case == "target":
        member["targets"][0]["recorded_hr_mean_bpm"] += 1
    elif case == "future":
        member["targets"][0]["history_windows"][0]["stop_input_row_index_exclusive"] += 1
    elif case == "cross_member":
        member["targets"][0]["history_windows"][0]["member_canonical_index"] = 1
    elif case == "split":
        member["split"] = "TEST"
    elif case == "extra_hr":
        package["columns"].append({"name": "recorded_hr_bpm", "source": "target", "unit": "bpm"})
    elif case == "authority":
        package["training_authorized"] = True
    elif case == "bool_alias":
        package["training_authorized"] = 0
    else:
        member["row_audit"].pop()
    with pytest.raises(ValueError, match="MODEL_INPUT_RECONSTRUCTION_MISMATCH"):
        module.check_response_model_input_package(rehash(package), contract, record, datasets)


@pytest.mark.parametrize("case", ["missing", "duplicate", "wrong_pin", "hash", "summary"])
def test_wrong_member_set_pin_or_incomplete_payload_fails_entire_assembly(inputs, case):
    record, datasets = deepcopy(inputs)
    contract = plan(record)
    if case == "missing":
        datasets.pop()
    elif case == "duplicate":
        datasets[-1] = datasets[0]
    elif case == "wrong_pin":
        datasets[0]["observations"][0]["workload_observation"]["gps_ground_speed_mps"] = 99
        datasets[0]["package_hash"] = canonical_hash(
            {k: v for k, v in datasets[0].items() if k != "package_hash"}
        )
    elif case == "hash":
        datasets[0]["package_hash"] = "f" * 64
    else:
        datasets[0]["payload_included"] = False
    with pytest.raises(ValueError):
        module.build_response_model_input_package(contract, record, datasets)


@pytest.mark.parametrize(
    "case", ["workload_time", "position", "contiguity", "mask_available", "unit"]
)
def test_binding_rechecks_newly_consumed_support_even_for_locally_repinned_payload(inputs, case):
    record, datasets = deepcopy(inputs)
    row = datasets[0]["observations"][1]
    if case == "workload_time":
        row["workload_observation"]["end_exercise_elapsed_ms"] = 5000
    elif case == "position":
        row["temporal_context"]["sequence_position"] = 99
    elif case == "contiguity":
        row["workload_observation"]["source_contiguous_with_previous"] = False
    elif case == "mask_available":
        row["environment_features"]["headwind_component_mps"]["available"] = False
    else:
        row["environment_features"]["headwind_component_mps"]["unit"] = "incorrect"
    record = repin_local_fixture(record, datasets)
    with pytest.raises(ValueError, match="MODEL_INPUT_"):
        module.build_response_model_input_package(plan(record), record, datasets)


def test_execution_bounds_and_output_hash_fail_closed(inputs, monkeypatch):
    record, datasets = inputs
    contract = plan(record)
    package = module.build_response_model_input_package(contract, record, datasets)
    package["input_package_hash"] = "f" * 64
    with pytest.raises(ValueError, match="PACKAGE_HASH_MISMATCH"):
        module.check_response_model_input_package(package, contract, record, datasets)
    monkeypatch.setattr(module, "MAX_TOTAL_OBSERVATIONS", 5)
    with pytest.raises(ValueError, match="COHORT_SIZE_LIMIT"):
        module.build_response_model_input_package(contract, record, datasets)


def test_nonfinite_or_boolean_selected_workload_is_masked_without_filling(inputs):
    record, datasets = deepcopy(inputs)
    for dataset in datasets:
        dataset["observations"][0]["workload_observation"]["gps_ground_speed_mps"] = True
    record = repin_local_fixture(record, datasets)
    package = module.build_response_model_input_package(plan(record), record, datasets)
    assert package["totals"]["model_input_row_count"] == 0
    assert package["members"][0]["input_arrays"]["values"][0][0] is None
    assert package["members"][0]["input_arrays"]["masks"][0][0] == "MISSING"


def long_local_fixture(inputs, masked_order=None):
    """400 synthetic intervals test default lookbacks; this is not live proof."""
    record, datasets = deepcopy(inputs)
    for dataset in datasets:
        template = deepcopy(dataset["observations"][0])
        stream = dataset["hr_streams"][0]
        start_utc = datetime.fromisoformat(dataset["routes"][0]["exercise_start_utc"])
        rows, slots = [], []
        for order in range(400):
            row = deepcopy(template)
            row.update(
                order_index=order,
                start_exercise_elapsed_ms=order * 1000,
                end_exercise_elapsed_ms=(order + 1) * 1000,
                row_id=canonical_hash([dataset["session_group_key"], 0, 0, order]),
                preparation_candidate=True,
                exclusion_reasons=[],
            )
            row["workload_observation"].update(
                order_index=order,
                start_exercise_elapsed_ms=order * 1000,
                end_exercise_elapsed_ms=(order + 1) * 1000,
                interval_ms=1000,
                gps_ground_speed_mps=2 + order / 1000,
                source_contiguous_with_previous=order > 0,
            )
            row["history_ref"].update(
                first_order_index=0, completed_end_order_index=order - 1 if order else None
            )
            row["temporal_context"].update(
                sequence_position=order,
                history_start_order_index=0,
                completed_history_end_order_index=order - 1 if order else None,
                current_workload_available_not_before_exercise_elapsed_ms=(order + 1) * 1000,
            )
            row["hr_label_ref"].update(
                status="COMPLETE",
                grid_start_index_inclusive=order,
                grid_stop_index_exclusive=order + 1,
                recorded_slot_count=1,
                unrecorded_grid_slot_count=0,
                expected_grid_slot_count=1,
                positive_finite_grid_sample_count=1,
                missing_or_invalid_grid_slot_count=0,
            )
            if order == masked_order:
                row["environment_features"]["headwind_component_mps"].update(
                    status="WITHHELD", available=False, value=None
                )
            rows.append(row)
            elapsed = stream["sample_grid_origin_us"] + order * stream["interval_us"]
            slots.append(
                {
                    "sample_index": order,
                    "value_bpm": 100 + order / 10,
                    "positive_finite": True,
                    "exercise_elapsed_us": elapsed,
                    "mapped_timestamp_utc": (
                        start_utc + timedelta(microseconds=elapsed)
                    ).isoformat(),
                }
            )
        stream.update(samples=slots, slot_count=400, positive_finite_sample_count=400)
        route = dataset["routes"][0]
        route.update(
            observation_count=400,
            supported_workload_observation_count=400,
            preparation_candidate_count=400,
            complete_hr_window_count=400,
        )
        route["sequences"][0].update(
            last_order_index=399, observation_count=400, end_exercise_elapsed_ms=400000
        )
        dataset.update(
            observations=rows,
            observation_count=400,
            source_observation_count=400,
            preparation_candidate_count=400,
            complete_hr_window_count=400,
            excluded_observation_count=0,
            hr_slot_count=400,
        )
        dataset["feature_status_counts"] = {
            name: dict(Counter(r["environment_features"][name]["status"] for r in rows))
            for name in dataset["feature_status_counts"]
        }
        dataset["component_status_counts"] = {
            name: dict(Counter(r["environment_components"][name]["status"] for r in rows))
            for name in dataset["component_status_counts"]
        }
    return repin_local_fixture(record, datasets), datasets


@pytest.mark.parametrize("masked_order,eligible_per_member", [(None, 281), (200, 161)])
def test_default_30_60_120_second_windows_on_long_observed_arrays_have_exact_coverage(
    inputs, masked_order, eligible_per_member
):
    record, datasets = long_local_fixture(inputs, masked_order)
    contract = build_response_experiment_manifest(record, experiment_id="default-history-analytic")
    package = module.build_response_model_input_package(contract, record, datasets)
    assert package["totals"]["source_observation_count"] == 1200
    assert package["totals"]["model_input_row_count"] == eligible_per_member * 3
    assert (
        module.check_response_model_input_package(package, contract, record, datasets)[
            "reconstruction_verified"
        ]
        is True
    )
    for member in package["members"]:
        if masked_order is None:
            assert member["targets"][0]["input_row_index"] == 119
            assert member["targets"][0]["recorded_hr_mean_bpm"] == 111.9
        else:
            assert member["coverage"]["exclusion_reason_counts"]["SELECTED_INPUT_MASKED"] == 120
            assert member["row_audit"][319]["eligible_for_experiment_input"] is False
            assert member["row_audit"][320]["eligible_for_experiment_input"] is True
        for target in member["targets"]:
            for ref in target["history_windows"]:
                assert ref["stop_input_row_index_exclusive"] == target["input_row_index"] + 1
                assert (
                    ref["first_input_row_index_inclusive"]
                    == target["input_row_index"] + 1 - ref["lookback_ms"] // 1000
                )
