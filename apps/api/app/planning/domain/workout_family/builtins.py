from ..common.refs import RegistryKey
from .models import (
    DoseConstraint,
    DoseValueKind,
    FamilyRef,
    PrescriptionStrictness,
    ProgressionPolicy,
    WorkoutFamilyDefinition,
    WorkoutFamilyRegistry,
    finalize_workout_family_registry,
)


WORKOUT_FAMILY_REGISTRY_VERSION_V0_1 = "workout_family_registry_v0.1"

KAYAK_EASY_TECHNICAL_KEY = "KAYAK_EASY_TECHNICAL"
KAYAK_LONG_AEROBIC_KEY = "KAYAK_LONG_AEROBIC"
STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY = (
    "STRENGTH_REFERENCE_AND_DEVELOPMENT"
)
RUN_EASY_AEROBIC_FALLBACK_KEY = "RUN_EASY_AEROBIC_FALLBACK"


def _modality(key: str) -> RegistryKey:
    return RegistryKey(
        registry="modality",
        key=key,
        registry_version="modality_registry_v0.1",
    )


def _sport(key: str) -> RegistryKey:
    return RegistryKey(
        registry="sport",
        key=key,
        registry_version="sport_registry_v0.1",
    )


def _duration(
    minimum_s: int,
    maximum_s: int,
    *,
    strictness: PrescriptionStrictness = PrescriptionStrictness.SOFT,
) -> DoseConstraint:
    return DoseConstraint(
        key="duration",
        value_kind=DoseValueKind.DURATION_S,
        strictness=strictness,
        min_value=minimum_s,
        max_value=maximum_s,
        unit="s",
    )


def _rpe(
    minimum: float,
    maximum: float,
    *,
    strictness: PrescriptionStrictness = PrescriptionStrictness.SOFT,
) -> DoseConstraint:
    return DoseConstraint(
        key="rpe",
        value_kind=DoseValueKind.RPE,
        strictness=strictness,
        min_value=minimum,
        max_value=maximum,
        unit="RPE_0_10",
    )


def _qualitative(
    key: str,
    value: str,
    *,
    strictness: PrescriptionStrictness,
) -> DoseConstraint:
    return DoseConstraint(
        key=key,
        value_kind=DoseValueKind.QUALITATIVE,
        strictness=strictness,
        qualitative_value=value,
    )


def kayak_easy_technical_v0_1() -> WorkoutFamilyDefinition:
    return WorkoutFamilyDefinition(
        family_ref=FamilyRef(
            KAYAK_EASY_TECHNICAL_KEY,
            "v0.1",
        ),
        family_registry_version=WORKOUT_FAMILY_REGISTRY_VERSION_V0_1,
        purpose=(
            "Easy kayak exposure with technical quality prioritized over "
            "physiological dose."
        ),
        modality_key=_modality("KAYAK"),
        sport_key=_sport("KAYAK_FLATWATER"),
        primary_capability_keys=("TECHNICAL_SKILL",),
        secondary_capability_keys=(
            "PERIPHERAL_OXIDATIVE_CAPACITY",
            "PADDLING_ECONOMY",
        ),
        required_stimulus_keys=("AEROBIC",),
        dose_constraints=(
            _duration(30 * 60, 45 * 60),
            _rpe(2.0, 3.0),
            _qualitative(
                "intensity_domain",
                "EASY",
                strictness=PrescriptionStrictness.SOFT,
            ),
        ),
        execution_priorities=(
            "TECHNIQUE_QUALITY",
            "EASY_EXECUTION",
        ),
        guardrails=(
            "NO_FORCED_HR_TARGET",
            "NO_INTENSITY_CHASING",
        ),
        measurement_observations=(
            "HEART_RATE_DESCRIPTIVE",
            "RPE",
            "TECHNICAL_QUALITY",
        ),
        required_feedback_fields=(
            "RPE",
            "EXECUTION_VS_EXPECTED",
            "PAIN",
            "UNUSUAL_ISSUE",
        ),
        progression_policy=ProgressionPolicy(
            allowed_dimensions=("DURATION",),
            max_dimensions_per_step=1,
            reduction_order=("DURATION",),
            protected_elements=("TECHNIQUE_QUALITY",),
        ),
        substitution_role=None,
    )


def kayak_long_aerobic_v0_1() -> WorkoutFamilyDefinition:
    return WorkoutFamilyDefinition(
        family_ref=FamilyRef(
            KAYAK_LONG_AEROBIC_KEY,
            "v0.1",
        ),
        family_registry_version=WORKOUT_FAMILY_REGISTRY_VERSION_V0_1,
        purpose=(
            "Longer kayak aerobic exposure with technique and response "
            "observability preserved."
        ),
        modality_key=_modality("KAYAK"),
        sport_key=_sport("KAYAK_FLATWATER"),
        primary_capability_keys=(
            "PERIPHERAL_OXIDATIVE_CAPACITY",
            "PADDLING_ECONOMY",
        ),
        secondary_capability_keys=(
            "LONG_DURATION_DURABILITY",
            "TECHNICAL_STABILITY_UNDER_FATIGUE",
            "PACING_COMPETENCE",
        ),
        required_stimulus_keys=("AEROBIC",),
        dose_constraints=(
            _duration(60 * 60, 75 * 60),
            _rpe(2.0, 4.0),
            _qualitative(
                "intensity_domain",
                "EASY_TO_LOW_MODERATE",
                strictness=PrescriptionStrictness.SOFT,
            ),
        ),
        execution_priorities=(
            "AEROBIC_CONTINUITY",
            "TECHNIQUE_QUALITY",
            "CONTROLLED_PACING",
        ),
        guardrails=(
            "NOT_A_MANDATORY_DURATION_QUOTA",
            "NO_HIGH_INTENSITY_ADDITION_BY_DEFAULT",
        ),
        measurement_observations=(
            "HEART_RATE_TRAJECTORY",
            "COMPARABLE_SPEED",
            "STROKE_RATE",
            "SPEED_STROKE_RATE_PROXY",
            "RPE",
            "TECHNICAL_STABILITY_OR_DRIFT",
        ),
        required_feedback_fields=(
            "RPE",
            "EXECUTION_VS_EXPECTED",
            "PAIN",
            "UNUSUAL_ISSUE",
        ),
        progression_policy=ProgressionPolicy(
            allowed_dimensions=("DURATION", "INTENSITY"),
            max_dimensions_per_step=1,
            reduction_order=("DURATION", "INTENSITY"),
            protected_elements=("TECHNIQUE_QUALITY",),
        ),
        substitution_role=None,
    )


def strength_reference_and_development_v0_1() -> WorkoutFamilyDefinition:
    return WorkoutFamilyDefinition(
        family_ref=FamilyRef(
            STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY,
            "v0.1",
        ),
        family_registry_version=WORKOUT_FAMILY_REGISTRY_VERSION_V0_1,
        purpose=(
            "Strength development while establishing a conservative "
            "personal reference without maximal testing."
        ),
        modality_key=_modality("STRENGTH"),
        sport_key=None,
        primary_capability_keys=("MAX_STRENGTH",),
        secondary_capability_keys=(
            "MUSCULOSKELETAL_ROBUSTNESS",
            "POWER_RFD",
        ),
        required_stimulus_keys=("STRENGTH",),
        dose_constraints=(
            DoseConstraint(
                key="main_movement_count",
                value_kind=DoseValueKind.MOVEMENT_COUNT,
                strictness=PrescriptionStrictness.SOFT,
                min_value=2,
                max_value=4,
                unit="movement",
            ),
            DoseConstraint(
                key="sets_per_main_movement",
                value_kind=DoseValueKind.SETS_PER_MOVEMENT,
                strictness=PrescriptionStrictness.SOFT,
                min_value=2,
                max_value=3,
                unit="set",
            ),
            DoseConstraint(
                key="rir",
                value_kind=DoseValueKind.RIR,
                strictness=PrescriptionStrictness.SOFT,
                min_value=2,
                max_value=4,
                unit="reps_in_reserve",
            ),
            _qualitative(
                "repetition_range",
                "MODERATE_LOW_REPETITIONS",
                strictness=PrescriptionStrictness.SOFT,
            ),
            _qualitative(
                "movement_families",
                (
                    "HORIZONTAL_PULL|HORIZONTAL_PRESS|"
                    "LOWER_BODY_FORCE|TRUNK"
                ),
                strictness=PrescriptionStrictness.SOFT,
            ),
        ),
        execution_priorities=(
            "CONTROLLED_FORCE_PRODUCTION",
            "REFERENCE_BUILDING",
            "TECHNICAL_LIFT_QUALITY",
        ),
        guardrails=(
            "NO_TRAINING_TO_FAILURE",
            "NO_GRINDING_REPETITIONS",
            "NO_MAXIMAL_TESTING_IN_INITIAL_REFERENCE_BUILD",
        ),
        measurement_observations=(
            "EXERCISE_SELECTION",
            "LOAD_USED",
            "REPETITIONS_COMPLETED",
            "RIR_ESTIMATE",
            "TECHNICAL_QUALITY",
        ),
        required_feedback_fields=(
            "RPE",
            "EXECUTION_VS_EXPECTED",
            "PAIN",
            "UNUSUAL_ISSUE",
        ),
        progression_policy=ProgressionPolicy(
            allowed_dimensions=(
                "LOAD",
                "SETS",
                "REPETITIONS",
                "MOVEMENT_COMPLEXITY",
            ),
            max_dimensions_per_step=1,
            reduction_order=("SETS", "LOAD", "REPETITIONS"),
            protected_elements=(
                "TECHNICAL_LIFT_QUALITY",
                "NO_FAILURE",
            ),
        ),
        substitution_role=None,
    )


def run_easy_aerobic_fallback_v0_1() -> WorkoutFamilyDefinition:
    return WorkoutFamilyDefinition(
        family_ref=FamilyRef(
            RUN_EASY_AEROBIC_FALLBACK_KEY,
            "v0.1",
        ),
        family_registry_version=WORKOUT_FAMILY_REGISTRY_VERSION_V0_1,
        purpose=(
            "Easy run used as a general aerobic fallback when kayak-specific "
            "training is unavailable or inappropriate."
        ),
        modality_key=_modality("RUN"),
        sport_key=_sport("RUNNING"),
        primary_capability_keys=("VO2_CAPACITY",),
        secondary_capability_keys=(
            "PERIPHERAL_OXIDATIVE_CAPACITY",
        ),
        required_stimulus_keys=("AEROBIC",),
        dose_constraints=(
            _duration(30 * 60, 45 * 60),
            _rpe(2.0, 3.0),
            _qualitative(
                "intensity_domain",
                "EASY",
                strictness=PrescriptionStrictness.SOFT,
            ),
        ),
        execution_priorities=(
            "EASY_EXECUTION",
            "GENERAL_AEROBIC_STIMULUS",
        ),
        guardrails=(
            "NO_KAYAK_SPECIFIC_EFFECT_ASSUMPTION",
            "NO_FORCED_HR_TARGET",
        ),
        measurement_observations=(
            "HEART_RATE_DESCRIPTIVE",
            "RPE",
        ),
        required_feedback_fields=(
            "RPE",
            "EXECUTION_VS_EXPECTED",
            "PAIN",
            "UNUSUAL_ISSUE",
        ),
        progression_policy=ProgressionPolicy(
            allowed_dimensions=("DURATION",),
            max_dimensions_per_step=1,
            reduction_order=("DURATION",),
            protected_elements=("EASY_EXECUTION",),
        ),
        substitution_role="GENERAL_AEROBIC_FALLBACK",
    )


def builtin_workout_family_registry_v0_1() -> WorkoutFamilyRegistry:
    return finalize_workout_family_registry(
        registry_version=WORKOUT_FAMILY_REGISTRY_VERSION_V0_1,
        families=(
            kayak_easy_technical_v0_1(),
            kayak_long_aerobic_v0_1(),
            strength_reference_and_development_v0_1(),
            run_easy_aerobic_fallback_v0_1(),
        ),
    )
