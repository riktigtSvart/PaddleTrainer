"""Fixed, bounded development experiment policy; no scientific authority."""

from typing import Literal

from pydantic import model_validator

from app.schemas.response_cohort import Identifier, Sha256
from app.schemas.response_experiment import StrictContract
from app.services.environment_replay_snapshot import canonical_hash


class ResponseBaselinePlan(StrictContract):
    schema_version: Literal["0.1"] = "0.1"
    baseline_version: Literal["0.1.0"] = "0.1.0"
    run_id: Identifier
    experiment_manifest_hash: Sha256
    input_package_hash: Sha256
    cohort_record_hash: Sha256
    cohort_index_hash: Sha256
    request_manifest_hash: Sha256
    adapter: Literal["DURATION_WEIGHTED_MEAN_PER_SELECTED_LOOKBACK"] = (
        "DURATION_WEIGHTED_MEAN_PER_SELECTED_LOOKBACK"
    )
    fit_scope: Literal["TRAIN_ONLY"] = "TRAIN_ONLY"
    session_weighting: Literal["EQUAL_TOTAL_WEIGHT_PER_NONEMPTY_TRAIN_SESSION"] = (
        "EQUAL_TOTAL_WEIGHT_PER_NONEMPTY_TRAIN_SESSION"
    )
    constant_baseline: Literal["SESSION_BALANCED_TRAIN_HR_MEAN"] = "SESSION_BALANCED_TRAIN_HR_MEAN"
    preprocessing: Literal["TRAIN_WEIGHTED_MEAN_AND_POPULATION_STD"] = (
        "TRAIN_WEIGHTED_MEAN_AND_POPULATION_STD"
    )
    numerical_constant_rule: Literal["TRAIN_RANGE_LE_1E_MINUS_12_TIMES_MAX_1_ABS"] = (
        "TRAIN_RANGE_LE_1E_MINUS_12_TIMES_MAX_1_ABS"
    )
    ridge_alpha: Literal[10.0] = 10.0
    ridge_min_nonempty_train_sessions: Literal[2] = 2
    ridge_intercept: Literal["UNPENALIZED_TRAIN_TARGET_MEAN"] = "UNPENALIZED_TRAIN_TARGET_MEAN"
    validation_role: Literal["DESCRIPTIVE_DEVELOPMENT_METRICS_ONLY"] = (
        "DESCRIPTIVE_DEVELOPMENT_METRICS_ONLY"
    )
    test_role: Literal["PAYLOAD_INTEGRITY_ONLY_NOT_ADAPTED_OR_SCORED"] = (
        "PAYLOAD_INTEGRITY_ONLY_NOT_ADAPTED_OR_SCORED"
    )
    hyperparameter_search_performed: Literal[False] = False
    automatic_model_selection_performed: Literal[False] = False
    missing_values_imputed: Literal[False] = False
    fixed_hr_shift_applied: Literal[False] = False
    physiological_lag_ms: None = None
    fatigue_target_used: Literal[False] = False
    pft_data_used: Literal[False] = False
    generalization_evidence_verified: Literal[False] = False
    training_authorized: Literal[False] = False
    numeric_output_authorized: Literal[False] = False
    plan_hash: Sha256

    @model_validator(mode="before")
    @classmethod
    def exact_numeric_policy(cls, value):
        if isinstance(value, dict):
            if "ridge_alpha" in value and type(value["ridge_alpha"]) is not float:
                raise ValueError("ridge_alpha requires the fixed JSON number 10.0")
            if (
                "ridge_min_nonempty_train_sessions" in value
                and type(value["ridge_min_nonempty_train_sessions"]) is not int
            ):
                raise ValueError("Session guard requires an integer")
        return value

    def committed_payload(self):
        body = self.model_dump(mode="json", exclude={"plan_hash"})
        return {**body, "plan_hash": canonical_hash(body)}
