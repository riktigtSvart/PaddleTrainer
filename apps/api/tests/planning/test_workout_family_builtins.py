from app.planning.domain.workout_family.builtins import (
    KAYAK_EASY_TECHNICAL_KEY,
    KAYAK_LONG_AEROBIC_KEY,
    RUN_EASY_AEROBIC_FALLBACK_KEY,
    STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY,
    builtin_workout_family_registry_v0_1,
)
from app.planning.domain.workout_family.models import DoseValueKind


def test_builtin_registry_contains_exactly_four_v0_1_families() -> None:
    registry = builtin_workout_family_registry_v0_1()

    assert {
        family.family_ref.family_key
        for family in registry.families
    } == {
        KAYAK_EASY_TECHNICAL_KEY,
        KAYAK_LONG_AEROBIC_KEY,
        STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY,
        RUN_EASY_AEROBIC_FALLBACK_KEY,
    }
    assert registry.verify_content_hash()


def test_easy_kayak_preserves_technique_and_does_not_prescribe_hr() -> None:
    family = builtin_workout_family_registry_v0_1().get(
        KAYAK_EASY_TECHNICAL_KEY
    )

    duration = family.dose_constraint("duration")
    rpe = family.dose_constraint("rpe")

    assert duration is not None
    assert duration.min_value == 30 * 60
    assert duration.max_value == 45 * 60
    assert rpe is not None
    assert (rpe.min_value, rpe.max_value) == (2.0, 3.0)
    assert "TECHNIQUE_QUALITY" in family.execution_priorities
    assert "NO_FORCED_HR_TARGET" in family.guardrails
    assert "HEART_RATE_DESCRIPTIVE" in family.measurement_observations
    assert family.progression_policy.reduction_order == ("DURATION",)
    assert (
        "TECHNIQUE_QUALITY"
        in family.progression_policy.protected_elements
    )


def test_long_kayak_reanchor_envelope_and_observability_are_explicit() -> None:
    family = builtin_workout_family_registry_v0_1().get(
        KAYAK_LONG_AEROBIC_KEY
    )

    duration = family.dose_constraint("duration")
    rpe = family.dose_constraint("rpe")

    assert duration is not None
    assert (duration.min_value, duration.max_value) == (
        60 * 60,
        75 * 60,
    )
    assert rpe is not None
    assert (rpe.min_value, rpe.max_value) == (2.0, 4.0)
    assert "NOT_A_MANDATORY_DURATION_QUOTA" in family.guardrails
    assert {
        "HEART_RATE_TRAJECTORY",
        "COMPARABLE_SPEED",
        "STROKE_RATE",
        "SPEED_STROKE_RATE_PROXY",
        "RPE",
        "TECHNICAL_STABILITY_OR_DRIFT",
    }.issubset(set(family.measurement_observations))


def test_strength_family_is_reference_building_not_max_test() -> None:
    family = builtin_workout_family_registry_v0_1().get(
        STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY
    )

    movement_count = family.dose_constraint("main_movement_count")
    sets = family.dose_constraint("sets_per_main_movement")
    rir = family.dose_constraint("rir")
    reps = family.dose_constraint("repetition_range")

    assert movement_count is not None
    assert (movement_count.min_value, movement_count.max_value) == (2, 4)
    assert sets is not None
    assert (sets.min_value, sets.max_value) == (2, 3)
    assert rir is not None
    assert (rir.min_value, rir.max_value) == (2, 4)
    assert reps is not None
    assert reps.value_kind == DoseValueKind.QUALITATIVE
    assert "NO_TRAINING_TO_FAILURE" in family.guardrails
    assert "NO_GRINDING_REPETITIONS" in family.guardrails
    assert "NO_MAXIMAL_TESTING_IN_INITIAL_REFERENCE_BUILD" in family.guardrails
    assert family.progression_policy.max_dimensions_per_step == 1


def test_run_fallback_does_not_claim_kayak_specific_effect() -> None:
    family = builtin_workout_family_registry_v0_1().get(
        RUN_EASY_AEROBIC_FALLBACK_KEY
    )

    assert family.substitution_role == "GENERAL_AEROBIC_FALLBACK"
    assert "NO_KAYAK_SPECIFIC_EFFECT_ASSUMPTION" in family.guardrails
    assert "TECHNICAL_SKILL" not in family.primary_capability_keys
    assert "PADDLING_ECONOMY" not in family.primary_capability_keys


def test_minimal_feedback_contract_is_common_to_all_builtins() -> None:
    registry = builtin_workout_family_registry_v0_1()
    expected = {
        "RPE",
        "EXECUTION_VS_EXPECTED",
        "PAIN",
        "UNUSUAL_ISSUE",
    }

    for family in registry.families:
        assert expected.issubset(
            set(family.required_feedback_fields)
        )


def test_pft_and_hiking_are_not_workout_families() -> None:
    registry = builtin_workout_family_registry_v0_1()
    keys = {
        family.family_ref.family_key
        for family in registry.families
    }

    assert "PFT" not in keys
    assert "PFT_PLUS_EASY_KAYAK" not in keys
    assert "HIKING" not in keys


def test_registry_hash_is_deterministic() -> None:
    left = builtin_workout_family_registry_v0_1()
    right = builtin_workout_family_registry_v0_1()

    assert left.content_hash == right.content_hash
