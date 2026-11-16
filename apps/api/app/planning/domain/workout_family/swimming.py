"""Extended registry; the historical v0.1 registry remains byte-for-byte stable."""
from dataclasses import replace
from .builtins import builtin_workout_family_registry_v0_1, run_easy_aerobic_fallback_v0_1, _sport, _modality, _duration, _rpe
from .models import FamilyRef, finalize_workout_family_registry


def builtin_workout_family_registry_v0_2():
    version = "workout_family_registry_v0.2"
    swim = replace(run_easy_aerobic_fallback_v0_1(), family_ref=FamilyRef("SWIM_EASY_AEROBIC", "v0.1"),
        family_registry_version=version, purpose="Easy pool swimming from declared independent swimming skill and current evidence.",
        sport_key=_sport("SWIMMING"), modality_key=_modality("SWIM"),
        primary_capability_keys=("PERIPHERAL_OXIDATIVE_CAPACITY",), secondary_capability_keys=(),
        dose_constraints=(_duration(1200, 3600), _rpe(2.0, 3.0)),
        guardrails=("INDEPENDENT_SWIMMING_DECLARED", "POOL_LENGTH_KNOWN", "NO_OLD_PEAK_PACE_TARGET", "NO_KAYAK_TECHNIQUE_SUBSTITUTION"))
    return finalize_workout_family_registry(registry_version=version,
        families=tuple(replace(f, family_registry_version=version) for f in builtin_workout_family_registry_v0_1().families) + (swim,))


def builtin_workout_family_registry_v0_3():
    """Time-based pool starts do not require a measured pool length.

    Keep v0.1/v0.2 hashes stable for existing saved reviews.
    """
    version = "workout_family_registry_v0.3"
    return finalize_workout_family_registry(registry_version=version, families=tuple(
        replace(f, family_registry_version=version,
            **({'guardrails': ('INDEPENDENT_SWIMMING_DECLARED', 'POOL_PRESENT',
                'POOL_LENGTH_KNOWN_FOR_DISTANCE_TARGETS', 'NO_OLD_PEAK_PACE_TARGET',
                'NO_KAYAK_TECHNIQUE_SUBSTITUTION')} if f.family_ref.family_key == 'SWIM_EASY_AEROBIC' else {}))
        for f in builtin_workout_family_registry_v0_2().families))
