from dataclasses import dataclass
from enum import StrEnum

from ..common.refs import RegistryKey
from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)


WORKOUT_FAMILY_REGISTRY_HASH_EXCLUDE_FIELDS = frozenset(
    {"content_hash"}
)


class PrescriptionStrictness(StrEnum):
    HARD = "hard"
    SOFT = "soft"
    FREE = "free"


class DoseValueKind(StrEnum):
    DURATION_S = "duration_s"
    RPE = "rpe"
    MOVEMENT_COUNT = "movement_count"
    SETS_PER_MOVEMENT = "sets_per_movement"
    RIR = "rir"
    QUALITATIVE = "qualitative"


class FamilyEntryGateStatus(StrEnum):
    """Entry-gate contribution only; not final workout authorization."""

    ELIGIBLE = "eligible"
    ELIGIBLE_WITH_CONSTRAINTS = "eligible_with_constraints"
    REDUCTION_ONLY = "reduction_only"
    DEFERRED_BY_GLOBAL_GATE = "deferred_by_global_gate"
    NOT_ELIGIBLE = "not_eligible"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True)
class FamilyRef:
    family_key: str
    family_version: str

    def __post_init__(self) -> None:
        if not self.family_key.strip():
            raise ValueError("family_key must be non-empty.")
        if not self.family_version.strip():
            raise ValueError("family_version must be non-empty.")


@dataclass(frozen=True)
class DoseConstraint:
    key: str
    value_kind: DoseValueKind
    strictness: PrescriptionStrictness

    min_value: float | int | None = None
    max_value: float | int | None = None
    qualitative_value: str | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("DoseConstraint key must be non-empty.")

        numeric = self.value_kind != DoseValueKind.QUALITATIVE

        if numeric:
            if self.qualitative_value is not None:
                raise ValueError(
                    "Numeric dose constraint cannot have qualitative_value."
                )
            if self.min_value is None and self.max_value is None:
                raise ValueError(
                    "Numeric dose constraint requires at least one bound."
                )
            if (
                self.min_value is not None
                and self.max_value is not None
                and self.min_value > self.max_value
            ):
                raise ValueError(
                    "DoseConstraint min_value must not exceed max_value."
                )
        else:
            if (
                self.qualitative_value is None
                or not self.qualitative_value.strip()
            ):
                raise ValueError(
                    "Qualitative dose constraint requires a value."
                )
            if self.min_value is not None or self.max_value is not None:
                raise ValueError(
                    "Qualitative dose constraint cannot have numeric bounds."
                )


@dataclass(frozen=True)
class ProgressionPolicy:
    allowed_dimensions: tuple[str, ...]
    max_dimensions_per_step: int | None
    reduction_order: tuple[str, ...]
    protected_elements: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.max_dimensions_per_step is not None
            and self.max_dimensions_per_step < 1
        ):
            raise ValueError(
                "max_dimensions_per_step must be positive or None."
            )


@dataclass(frozen=True)
class WorkoutFamilyDefinition:
    family_ref: FamilyRef
    family_registry_version: str

    purpose: str
    modality_key: RegistryKey
    sport_key: RegistryKey | None

    primary_capability_keys: tuple[str, ...]
    secondary_capability_keys: tuple[str, ...]
    required_stimulus_keys: tuple[str, ...]

    dose_constraints: tuple[DoseConstraint, ...]
    execution_priorities: tuple[str, ...]
    guardrails: tuple[str, ...]
    measurement_observations: tuple[str, ...]
    required_feedback_fields: tuple[str, ...]

    progression_policy: ProgressionPolicy

    substitution_role: str | None
    evidence_claim_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.family_registry_version.strip():
            raise ValueError(
                "family_registry_version must be non-empty."
            )
        if not self.purpose.strip():
            raise ValueError("purpose must be non-empty.")
        if len(set(self.required_stimulus_keys)) != len(
            self.required_stimulus_keys
        ):
            raise ValueError(
                "required_stimulus_keys must be unique."
            )

        dose_keys = tuple(item.key for item in self.dose_constraints)
        if len(set(dose_keys)) != len(dose_keys):
            raise ValueError("DoseConstraint keys must be unique.")

    def dose_constraint(
        self,
        key: str,
    ) -> DoseConstraint | None:
        return next(
            (
                item
                for item in self.dose_constraints
                if item.key == key
            ),
            None,
        )


@dataclass(frozen=True)
class WorkoutFamilyRegistry:
    registry_version: str
    families: tuple[WorkoutFamilyDefinition, ...]
    content_hash_algorithm: str
    content_hash: str

    def __post_init__(self) -> None:
        if not self.registry_version.strip():
            raise ValueError("registry_version must be non-empty.")

        refs = tuple(
            (
                family.family_ref.family_key,
                family.family_ref.family_version,
            )
            for family in self.families
        )
        if len(refs) != len(set(refs)):
            raise ValueError(
                "Workout family refs must be unique in a registry."
            )

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=WORKOUT_FAMILY_REGISTRY_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )

    def get(
        self,
        family_key: str,
        family_version: str = "v0.1",
    ) -> WorkoutFamilyDefinition:
        for family in self.families:
            if (
                family.family_ref.family_key == family_key
                and family.family_ref.family_version == family_version
            ):
                return family

        raise KeyError(
            f"Workout family not found: "
            f"{family_key}@{family_version}"
        )


def finalize_workout_family_registry(
    *,
    registry_version: str,
    families: tuple[WorkoutFamilyDefinition, ...],
) -> WorkoutFamilyRegistry:
    ordered = tuple(
        sorted(
            families,
            key=lambda family: (
                family.family_ref.family_key,
                family.family_ref.family_version,
            ),
        )
    )

    provisional = WorkoutFamilyRegistry(
        registry_version=registry_version,
        families=ordered,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=WORKOUT_FAMILY_REGISTRY_HASH_EXCLUDE_FIELDS,
    )

    return WorkoutFamilyRegistry(
        registry_version=provisional.registry_version,
        families=provisional.families,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )


@dataclass(frozen=True)
class FamilyEntryGateAssessment:
    family_ref: FamilyRef
    entry_gate_decision_hash: str
    status: FamilyEntryGateStatus
    stimulus_gate_statuses: tuple[tuple[str, str], ...]
    reason_codes: tuple[str, ...]
    build_authorized: bool
    dose_reduction_required: bool
