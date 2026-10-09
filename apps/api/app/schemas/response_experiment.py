"""Strict retrospective experiment commitments, without fitted data or authority."""

import hashlib
import json
from typing import Annotated, Literal, Self, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.response_cohort import CanonicalUuid, Identifier, Sha256

WorkloadFeature = Literal[
    "gps_ground_speed_mps",
    "ground_speed_change_from_previous_mps",
    "ground_speed_change_rate_mps2",
    "absolute_bearing_change_from_previous_deg",
]
EnvironmentFeature = Literal[
    "air_temperature_c",
    "weather_wind_speed_mps",
    "weather_wind_direction_from_deg",
    "weather_wind_gust_mps",
    "headwind_component_mps",
    "tailwind_component_mps",
    "crosswind_magnitude_mps",
    "relative_air_speed_mps",
    "water_level_cm",
    "discharge_m3_s",
    "water_temperature_c",
]
LookbackMs = Annotated[int, Field(strict=True, gt=0, le=600_000)]


class StrictContract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def exact_boolean_literals(cls, value):
        # Literal[False] alone may accept 0 through Python's bool/int equality.
        if isinstance(value, dict):
            for name, info in cls.model_fields.items():
                literals = get_args(info.annotation)
                if (
                    name in value
                    and get_origin(info.annotation) is Literal
                    and literals
                    and all(type(item) is bool for item in literals)
                    and type(value[name]) is not bool
                ):
                    raise ValueError("Boolean policy commitments require JSON booleans")
        return value


class ExperimentCohortReference(StrictContract):
    record_schema_version: Literal["0.1"] = "0.1"
    record_hash: Sha256
    cohort_index_hash: Sha256
    request_manifest_hash: Sha256
    owner_id: CanonicalUuid


class ExperimentMember(StrictContract):
    provider: Literal["POLAR"] = "POLAR"
    athlete_id: CanonicalUuid
    session_external_id: Identifier
    split: Literal["TRAIN", "VALIDATION", "TEST"]


class ExperimentContext(StrictContract):
    declared_modality: Literal["KAYAK_WATER"] = "KAYAK_WATER"
    modality_claim_scope: Literal["REQUEST_DECLARATION_ONLY"] = "REQUEST_DECLARATION_ONLY"
    workload_semantics: Literal["OBSERVED_GPS_MOTION_PROXY_NOT_MEASURED_POWER"] = (
        "OBSERVED_GPS_MOTION_PROXY_NOT_MEASURED_POWER"
    )
    response_scope: Literal["RECORDED_SENSOR_HR_ONLY"] = "RECORDED_SENSOR_HR_ONLY"
    sensor_identity_or_quality_promoted: Literal[False] = False


class RecordedHrTarget(StrictContract):
    variable: Literal["recorded_hr_bpm"] = "recorded_hr_bpm"
    unit: Literal["bpm"] = "bpm"
    aggregation: Literal["MEAN_OF_POSITIVE_FINITE_SAMPLES"] = "MEAN_OF_POSITIVE_FINITE_SAMPLES"
    coverage: Literal["COMPLETE_VERIFIED_EXPORT_GRID_WINDOW"] = (
        "COMPLETE_VERIFIED_EXPORT_GRID_WINDOW"
    )
    window_semantics: Literal["HALF_OPEN_START_INCLUSIVE_END_EXCLUSIVE"] = (
        "HALF_OPEN_START_INCLUSIVE_END_EXCLUSIVE"
    )
    label_used_as_predictor: Literal[False] = False
    hr_derived_predictors_used: Literal[False] = False
    physiological_ground_truth_claimed: Literal[False] = False


class ExperimentInputs(StrictContract):
    workload_features: list[WorkloadFeature] = Field(
        default_factory=lambda: ["gps_ground_speed_mps"], min_length=1, max_length=4
    )
    environment_features: list[EnvironmentFeature] = Field(
        default_factory=lambda: [
            "air_temperature_c",
            "headwind_component_mps",
            "crosswind_magnitude_mps",
        ],
        max_length=11,
    )
    source_masks: Literal["PRESERVE_AVAILABLE_MISSING_WITHHELD_NOT_APPLICABLE"] = (
        "PRESERVE_AVAILABLE_MISSING_WITHHELD_NOT_APPLICABLE"
    )
    model_row_requirement: Literal["ALL_SELECTED_VALUES_AVAILABLE_FINITE"] = (
        "ALL_SELECTED_VALUES_AVAILABLE_FINITE"
    )
    unlabelled_workload_history: Literal["PRESERVE_FOR_CONDITIONING"] = "PRESERVE_FOR_CONDITIONING"
    raw_observations_preserved: Literal[True] = True
    missing_value_imputation: Literal["NONE"] = "NONE"
    withheld_values_promoted: Literal[False] = False

    @model_validator(mode="after")
    def unique_features(self) -> Self:
        for items in (self.workload_features, self.environment_features):
            if len(set(items)) != len(items):
                raise ValueError("Duplicate feature selection")
        return self


class ExperimentTemporalPolicy(StrictContract):
    lookback_windows_ms: list[LookbackMs] = Field(
        default_factory=lambda: [30_000, 60_000, 120_000], min_length=1, max_length=8
    )
    history_anchor: Literal["TARGET_WINDOW_END_RETROSPECTIVE_CONDITIONING"] = (
        "TARGET_WINDOW_END_RETROSPECTIVE_CONDITIONING"
    )
    history_scope: Literal["SAME_SESSION_ROUTE_EXERCISE_SEQUENCE_ONLY"] = (
        "SAME_SESSION_ROUTE_EXERCISE_SEQUENCE_ONLY"
    )
    history_coverage: Literal["REQUIRE_COMPLETE_SELECTED_LOOKBACKS"] = (
        "REQUIRE_COMPLETE_SELECTED_LOOKBACKS"
    )
    future_workload_used: Literal[False] = False
    sequence_boundaries_preserved: Literal[True] = True
    initial_physiological_state: Literal["UNKNOWN_RETAINED"] = "UNKNOWN_RETAINED"
    censored_history_and_recovery_preserved: Literal[True] = True
    fixed_hr_shift_applied: Literal[False] = False
    physiological_lag_ms: None = None
    export_clock_mapping_role: Literal["TECHNICAL_TIMESTAMP_ALIGNMENT_ONLY"] = (
        "TECHNICAL_TIMESTAMP_ALIGNMENT_ONLY"
    )

    @model_validator(mode="after")
    def unique_lookbacks(self) -> Self:
        if len(set(self.lookback_windows_ms)) != len(self.lookback_windows_ms):
            raise ValueError("Duplicate history window")
        return self


class ExperimentEvaluationPolicy(StrictContract):
    split_scope: Literal["EXACT_ARCHIVED_WHOLE_SESSION_ASSIGNMENTS"] = (
        "EXACT_ARCHIVED_WHOLE_SESSION_ASSIGNMENTS"
    )
    fitted_preprocessing_scope: Literal["TRAIN_ONLY"] = "TRAIN_ONLY"
    data_driven_feature_selection_scope: Literal["TRAIN_ONLY"] = "TRAIN_ONLY"
    validation_role: Literal["MODEL_SELECTION_ONLY"] = "MODEL_SELECTION_ONLY"
    test_role: Literal["FINAL_FROZEN_EVALUATION_ONLY"] = "FINAL_FROZEN_EVALUATION_ONLY"
    reporting_unit: Literal["PER_SESSION_WITH_LABEL_AND_INPUT_COVERAGE"] = (
        "PER_SESSION_WITH_LABEL_AND_INPUT_COVERAGE"
    )
    requested_metrics: list[Literal["MAE_BPM", "RMSE_BPM", "MEAN_SIGNED_ERROR_BPM"]] = Field(
        default_factory=lambda: ["MAE_BPM", "RMSE_BPM", "MEAN_SIGNED_ERROR_BPM"],
        min_length=1,
        max_length=3,
    )
    independence_between_sessions_claimed: Literal[False] = False

    @model_validator(mode="after")
    def unique_metrics(self) -> Self:
        if len(set(self.requested_metrics)) != len(self.requested_metrics):
            raise ValueError("Duplicate requested metric")
        return self


class PftIntegrationPolicy(StrictContract):
    pft_features_used: Literal[False] = False
    fitness_or_fatigue_targets_used: Literal[False] = False
    readiness_score_computed: Literal[False] = False
    measurement_and_interpretation_separated: Literal[True] = True
    future_baseline_grouping: Literal["ATHLETE_MODALITY_PROTOCOL_FEATURE_STIMULUS"] = (
        "ATHLETE_MODALITY_PROTOCOL_FEATURE_STIMULUS"
    )
    future_baseline_cutoff: Literal["REFERENCE_AVAILABLE_STRICTLY_BEFORE_TARGET_SESSION"] = (
        "REFERENCE_AVAILABLE_STRICTLY_BEFORE_TARGET_SESSION"
    )
    future_baseline_update_order: Literal["COMPARE_THEN_ELIGIBLE_UPDATE"] = (
        "COMPARE_THEN_ELIGIBLE_UPDATE"
    )


class ResponseExperimentManifest(StrictContract):
    schema_version: Literal["0.1"]
    experiment_id: Identifier
    task: Literal["RETROSPECTIVE_HR_RESPONSE_WITHIN_ATHLETE"] = (
        "RETROSPECTIVE_HR_RESPONSE_WITHIN_ATHLETE"
    )
    cohort: ExperimentCohortReference
    members: list[ExperimentMember] = Field(min_length=3, max_length=20)
    context: ExperimentContext = Field(default_factory=ExperimentContext)
    target: RecordedHrTarget = Field(default_factory=RecordedHrTarget)
    inputs: ExperimentInputs = Field(default_factory=ExperimentInputs)
    temporal: ExperimentTemporalPolicy = Field(default_factory=ExperimentTemporalPolicy)
    evaluation: ExperimentEvaluationPolicy = Field(default_factory=ExperimentEvaluationPolicy)
    pft: PftIntegrationPolicy = Field(default_factory=PftIntegrationPolicy)
    experiment_manifest_hash: Sha256

    @model_validator(mode="after")
    def whole_session_partitions(self) -> Self:
        groups = {(m.provider, m.athlete_id, m.session_external_id) for m in self.members}
        if len(groups) != len(self.members):
            raise ValueError("Duplicate experiment session")
        if any(m.athlete_id != self.cohort.owner_id for m in self.members):
            raise ValueError("Experiment member owner differs from cohort pin")
        if {m.split for m in self.members} != {"TRAIN", "VALIDATION", "TEST"}:
            raise ValueError("All evaluation partitions must be nonempty")
        return self

    def canonical_body(self) -> dict:
        payload = self.model_dump(mode="json", exclude={"experiment_manifest_hash"})
        payload["members"].sort(
            key=lambda member: (
                member["provider"],
                member["athlete_id"],
                member["session_external_id"],
            )
        )
        for key in ("workload_features", "environment_features"):
            payload["inputs"][key].sort()
        payload["temporal"]["lookback_windows_ms"].sort()
        payload["evaluation"]["requested_metrics"].sort()
        return payload

    def computed_hash(self) -> str:
        raw = json.dumps(
            self.canonical_body(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def committed_payload(self) -> dict:
        return {**self.canonical_body(), "experiment_manifest_hash": self.computed_hash()}
