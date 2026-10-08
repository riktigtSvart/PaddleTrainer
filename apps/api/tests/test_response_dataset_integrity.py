from copy import deepcopy

import pytest
from test_environment_replay_snapshot import inputs as _inputs_fixture
from test_training_data_readiness_audit import sources as _sources_fixture

from app.services import response_dataset_integrity as module
from app.services.environment_replay_snapshot import canonical_hash, dataset_from_inputs
from app.services.route_response_dataset import summarize_route_response_dataset

inputs = _inputs_fixture
sources = _sources_fixture


@pytest.fixture
def dataset(inputs):
    return dataset_from_inputs(
        {
            key: inputs[key]
            for key in (
                "expected_response_input",
                "trusted_environment",
                "provider_selection",
                "weather_source",
            )
        },
        route_session=inputs["route_session"],
        sample_session=inputs["sample_session"],
        athlete_id=inputs["athlete_id"],
        session_external_id=inputs["session_external_id"],
        clocks=inputs["hr_timebase_snapshots"],
        declarations=[],
    )


def rehash(value):
    value["package_hash"] = canonical_hash({k: v for k, v in value.items() if k != "package_hash"})


def test_full_data_is_checked_read_only_without_promoting_source_verification(dataset):
    before = deepcopy(dataset)
    result = module.check_response_dataset_integrity(dataset)
    assert dataset == before and result["hr_window_status_counts"] == {"COMPLETE": 2}
    assert result["claim_scope"] == "PAYLOAD_INTEGRITY_AND_INTERNAL_CONSISTENCY_ONLY"
    assert "source_evidence_verified" not in result


def test_hash_changes_and_summary_are_not_valid_full_payloads(dataset):
    with pytest.raises(ValueError, match="DATASET_FULL_PAYLOAD_REQUIRED"):
        module.check_response_dataset_integrity(summarize_route_response_dataset(dataset))
    dataset["hr_streams"][0]["samples"][0]["value_bpm"] += 1
    with pytest.raises(ValueError, match="DATASET_PAYLOAD_HASH_MISMATCH"):
        module.check_response_dataset_integrity(dataset)


@pytest.mark.parametrize(
    "case",
    [
        "count",
        "excluded_count",
        "source_count",
        "feature_count",
        "component_count",
        "row_id",
        "route_count",
        "duplicate_row",
        "row_route",
        "row_split",
        "stream_split",
        "stream_length",
        "slot_index",
        "mask",
        "grid_elapsed",
        "grid_utc",
        "label_stream",
        "grid_window",
        "recorded",
        "positives",
        "label_status",
        "future_history",
        "history_route",
        "history_start",
        "sequence_count",
        "censored",
        "initial_state",
        "unavailable_feature",
        "hr_predictor",
        "authorization",
        "fixed_shift",
        "imputation",
    ],
)
def test_rehashed_content_cannot_hide_broken_internal_references_or_policies(dataset, case):
    row, stream = dataset["observations"][1], dataset["hr_streams"][0]
    actions = {
        "count": lambda: dataset.update(observation_count=99),
        "excluded_count": lambda: dataset.update(excluded_observation_count=99),
        "source_count": lambda: dataset.update(source_observation_count=99),
        "feature_count": lambda: dataset["feature_status_counts"]["water_temperature_c"].update(
            MISSING=99
        ),
        "component_count": lambda: dataset["component_status_counts"]["weather"].update(
            AVAILABLE=99
        ),
        "row_id": lambda: row.update(row_id="a" * 64),
        "route_count": lambda: dataset.update(route_count=99),
        "duplicate_row": lambda: row.update(row_id=dataset["observations"][0]["row_id"]),
        "row_route": lambda: row.update(route_index=99),
        "row_split": lambda: row.update(split="TEST"),
        "stream_split": lambda: stream.update(split="TEST"),
        "stream_length": lambda: stream["samples"].pop(),
        "slot_index": lambda: stream["samples"][1].update(sample_index=99),
        "mask": lambda: stream["samples"][1].update(positive_finite=False),
        "grid_elapsed": lambda: stream["samples"][1].update(exercise_elapsed_us=1500001),
        "grid_utc": lambda: stream["samples"][1].update(
            mapped_timestamp_utc="2026-09-30T15:00:02+00:00"
        ),
        "label_stream": lambda: row["hr_label_ref"].update(stream_id="unknown"),
        "grid_window": lambda: row["hr_label_ref"].update(grid_start_index_inclusive=0),
        "recorded": lambda: row["hr_label_ref"].update(recorded_slot_count=99),
        "positives": lambda: row["hr_label_ref"].update(positive_finite_grid_sample_count=99),
        "label_status": lambda: row["hr_label_ref"].update(status="NO_SAMPLES"),
        "future_history": lambda: row["history_ref"].update(completed_end_order_index=1),
        "history_route": lambda: row["history_ref"].update(route_index=99),
        "history_start": lambda: row["history_ref"].update(first_order_index=1),
        "sequence_count": lambda: dataset["routes"][0].update(sequence_count=99),
        "censored": lambda: dataset["routes"][0]["sequences"][0].update(
            post_observation_recovery_censored=False
        ),
        "initial_state": lambda: dataset["routes"][0]["sequences"][0].update(
            initial_physiological_state="KNOWN"
        ),
        "unavailable_feature": lambda: row["environment_features"]["water_temperature_c"].update(
            value=20
        ),
        "hr_predictor": lambda: row["hr_label_ref"].update(label_used_as_predictor=True),
        "authorization": lambda: dataset.update(training_authorized=True),
        "fixed_shift": lambda: dataset["policy"].update(fixed_hr_shift_applied=True),
        "imputation": lambda: dataset["policy"].update(feature_missing_values_imputed=True),
    }
    actions[case]()
    rehash(dataset)
    with pytest.raises(ValueError):
        module.check_response_dataset_integrity(dataset)


@pytest.mark.parametrize(
    "budget", ["MAX_DATASET_BYTES", "MAX_OBSERVATIONS", "MAX_HR_SLOTS", "MAX_ROUTES"]
)
def test_input_shape_and_serialized_size_budgets_are_explicit(dataset, monkeypatch, budget):
    monkeypatch.setattr(module, budget, 0)
    with pytest.raises(ValueError, match="DATASET_EXECUTION_SIZE_LIMIT"):
        module.check_response_dataset_integrity(dataset)


def test_nonfinite_and_malformed_payloads_cannot_be_valid(dataset):
    dataset["hr_streams"][0]["samples"][0]["value_bpm"] = float("nan")
    with pytest.raises(ValueError):
        module.check_response_dataset_integrity(dataset)
    for value in ({}, None, []):
        with pytest.raises(ValueError):
            module.check_response_dataset_integrity(value)


def test_no_verified_clock_remains_unmapped_without_inventing_a_grid(inputs):
    value = dataset_from_inputs(
        {
            key: inputs[key]
            for key in (
                "expected_response_input",
                "trusted_environment",
                "provider_selection",
                "weather_source",
            )
        },
        route_session=inputs["route_session"],
        sample_session=inputs["sample_session"],
        athlete_id=inputs["athlete_id"],
        session_external_id=inputs["session_external_id"],
        clocks=[],
        declarations=[],
    )
    assert module.check_response_dataset_integrity(value)["internal_references_verified"] is True
    assert all(s["exercise_elapsed_us"] is None for s in value["hr_streams"][0]["samples"])


def test_unlabelled_tail_retains_prior_history_and_unrecorded_grid_slots(dataset):
    stream = dataset["hr_streams"][0]
    stream["samples"] = stream["samples"][:2]
    stream.update(slot_count=2, positive_finite_sample_count=2)
    dataset["hr_slot_count"] = 2
    dataset["preparation_candidate_count"] = 1
    dataset["excluded_observation_count"] = 1
    dataset["routes"][0].update(complete_hr_window_count=1, preparation_candidate_count=1)
    dataset["complete_hr_window_count"] = 1
    row = dataset["observations"][1]
    row["preparation_candidate"] = False
    row["hr_label_ref"].update(
        status="NO_SAMPLES",
        recorded_slot_count=0,
        unrecorded_grid_slot_count=2,
        positive_finite_grid_sample_count=0,
        missing_or_invalid_grid_slot_count=2,
    )
    rehash(dataset)
    assert module.check_response_dataset_integrity(dataset)["hr_window_status_counts"] == {
        "COMPLETE": 1,
        "NO_SAMPLES": 1,
    }
    assert row["history_ref"]["completed_end_order_index"] == 0
