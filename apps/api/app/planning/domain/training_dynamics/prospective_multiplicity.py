from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc
from .models import EffectEvidenceLevel
from .prospective_cohort import (
    ProspectiveIssuanceCohortSource,
    ProspectiveValidationFamilyKey,
)
from .prospective_issuance import (
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01,
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01,
    PersonalResponsePredictionIssuanceContract,
)


PROSPECTIVE_MULTIPLICITY_GUARD_SCHEMA_V01 = (
    "prospective-multiplicity-guard-v0.1"
)

PROSPECTIVE_MULTIPLICITY_GUARD_RULES_V01 = (
    "prospective-multiplicity-guard-rules-v0.1"
)

PROSPECTIVE_MULTIPLICITY_GUARD_HASH_EXCLUDE_FIELDS = (
    frozenset(
        {
            "guard_id",
            "created_at",
            "content_hash",
        }
    )
)


class ProspectiveMultiplicityMethod(StrEnum):
    BONFERRONI_FWER = "bonferroni_fwer"


@dataclass(frozen=True)
class ProspectiveValidationFamilyCensusEntry:
    family_key: ProspectiveValidationFamilyKey

    issuance_count: int

    issuance_ids: tuple[str, ...]
    issuance_content_hashes: tuple[str, ...]

    first_issuance_persisted_at: datetime
    last_issuance_persisted_at: datetime


@dataclass(frozen=True)
class ProspectiveValidationMultiplicityGuard:
    """Outcome-independent multiplicity universe for prospective validation.

    Every exact model ? predictor ? response family with at least one
    durable issuance by `as_of` is retained.

    No outcome result is used to decide which families enter the census.

    C2 does not establish prospective validation.
    """

    guard_id: str
    schema_version: str
    rules_version: str

    athlete_id: str
    target_family_key: ProspectiveValidationFamilyKey

    as_of: datetime

    audit_scan_complete: bool

    family_count: int
    target_family_present: bool
    target_family_issuance_count: int

    family_census: tuple[
        ProspectiveValidationFamilyCensusEntry,
        ...,
    ]

    multiplicity_method: ProspectiveMultiplicityMethod

    familywise_alpha_numerator: int
    familywise_alpha_denominator: int

    adjusted_alpha_numerator: int | None
    adjusted_alpha_denominator: int | None

    anti_selection_guard_passed: bool
    multiplicity_guard_passed: bool

    validation_assessment_input_eligible: bool

    evidence_level_ceiling: EffectEvidenceLevel
    association_supported: bool

    prospective_validation_established: bool
    causal_attribution_established: bool
    effect_inference_authorized: bool
    readiness_inference_authorized: bool
    performance_prediction_authorized: bool
    prescription_change_authorized: bool
    planning_authorized: bool

    created_at: datetime

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=(
                    PROSPECTIVE_MULTIPLICITY_GUARD_HASH_EXCLUDE_FIELDS
                ),
            )
            == self.content_hash
        )


def _require_non_empty(
    value: str,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be a non-empty string."
        )

    return value


def _family_identity(
    family: ProspectiveValidationFamilyKey,
) -> tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
]:
    return (
        family.model_id,
        family.model_version,
        family.predictor_key.metric_key,
        family.predictor_key.unit or "",
        family.response_key.metric_key,
        family.response_key.unit or "",
        family.response_key.response_timing.value,
        family.response_key.stimulus_modality_key,
    )


def _validate_family(
    family: ProspectiveValidationFamilyKey,
) -> None:
    _require_non_empty(
        family.model_id,
        field_name="family.model_id",
    )

    _require_non_empty(
        family.model_version,
        field_name="family.model_version",
    )

    _require_non_empty(
        family.predictor_key.metric_key,
        field_name="family.predictor_key.metric_key",
    )

    _require_non_empty(
        family.response_key.metric_key,
        field_name="family.response_key.metric_key",
    )

    _require_non_empty(
        family.response_key.stimulus_modality_key,
        field_name=(
            "family.response_key.stimulus_modality_key"
        ),
    )


def _family_from_issuance(
    issuance: PersonalResponsePredictionIssuanceContract,
) -> ProspectiveValidationFamilyKey:
    return ProspectiveValidationFamilyKey(
        model_id=issuance.model_id,
        model_version=issuance.model_version,
        predictor_key=issuance.predictor_key,
        response_key=issuance.response_key,
    )


def _validate_issuance(
    *,
    source: ProspectiveIssuanceCohortSource,
    athlete_id: str,
    as_of: datetime,
) -> datetime:
    issuance = source.issuance

    if not issuance.verify_content_hash():
        raise ValueError(
            "Multiplicity census issuance content hash "
            "does not verify."
        )

    if (
        issuance.schema_version
        != PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01
        or issuance.rules_version
        != PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01
    ):
        raise ValueError(
            "Unsupported multiplicity census issuance."
        )

    if issuance.athlete_id != athlete_id:
        raise ValueError(
            "Multiplicity census issuance athlete differs."
        )

    if (
        issuance.response_prediction_available is not True
        or issuance.evidence_level_ceiling
        != EffectEvidenceLevel.ASSOCIATION_SUPPORTED
        or issuance.association_supported is not True
    ):
        raise ValueError(
            "Multiplicity census issuance lacks required "
            "bounded prediction authority."
        )

    if any(
        (
            issuance.prospective_validation_established,
            issuance.causal_attribution_established,
            issuance.effect_inference_authorized,
            issuance.readiness_inference_authorized,
            issuance.performance_prediction_authorized,
            issuance.prescription_change_authorized,
            issuance.planning_authorized,
        )
    ):
        raise ValueError(
            "Multiplicity census issuance contains "
            "unsupported stronger authority."
        )

    persisted = to_utc(
        source.persisted_at,
        field_name="issuance.persisted_at",
    )

    prediction_at = to_utc(
        issuance.prediction_at,
        field_name="issuance.prediction_at",
    )

    information_cutoff = to_utc(
        issuance.information_cutoff_at,
        field_name="issuance.information_cutoff_at",
    )

    if persisted < prediction_at:
        raise ValueError(
            "Issuance persistence predates prediction_at."
        )

    if persisted < information_cutoff:
        raise ValueError(
            "Issuance persistence predates information cutoff."
        )

    if persisted > as_of:
        raise ValueError(
            "Multiplicity census contains future issuance."
        )

    return persisted


def build_prospective_validation_multiplicity_guard(
    *,
    athlete_id: str,
    target_family_key: ProspectiveValidationFamilyKey,
    as_of: datetime,
    issuance_sources: tuple[
        ProspectiveIssuanceCohortSource,
        ...,
    ],
    audit_scan_complete: bool,
    created_at: datetime,
) -> ProspectiveValidationMultiplicityGuard:
    """Freeze the complete-as-known prospective hypothesis universe.

    The multiplicity universe is based only on durable issuance existence,
    never on later outcomes.

    Bonferroni is intentionally conservative and outcome-independent:
        familywise alpha = 1/20
        per-family alpha = 1/(20 * family_count)

    C3 may use this threshold, but C2 itself performs no validation test.
    """

    athlete = _require_non_empty(
        athlete_id,
        field_name="athlete_id",
    )

    _validate_family(
        target_family_key
    )

    cutoff = to_utc(
        as_of,
        field_name="as_of",
    )

    created = to_utc(
        created_at,
        field_name="created_at",
    )

    if created < cutoff:
        raise ValueError(
            "Multiplicity guard cannot be created "
            "before as_of."
        )

    if not isinstance(
        audit_scan_complete,
        bool,
    ):
        raise ValueError(
            "audit_scan_complete must be boolean."
        )

    issuance_ids = set()

    grouped: dict[
        tuple[str, str, str, str, str, str, str, str],
        list[
            tuple[
                PersonalResponsePredictionIssuanceContract,
                datetime,
            ]
        ],
    ] = {}

    family_by_identity = {}

    for source in issuance_sources:
        issuance = source.issuance

        if issuance.issuance_id in issuance_ids:
            raise ValueError(
                "Duplicate issuance artifact identity "
                "in multiplicity census source."
            )

        issuance_ids.add(
            issuance.issuance_id
        )

        persisted = _validate_issuance(
            source=source,
            athlete_id=athlete,
            as_of=cutoff,
        )

        family = _family_from_issuance(
            issuance
        )

        _validate_family(
            family
        )

        identity = _family_identity(
            family
        )

        family_by_identity[
            identity
        ] = family

        grouped.setdefault(
            identity,
            [],
        ).append(
            (
                issuance,
                persisted,
            )
        )

    census_entries = []

    for identity in sorted(grouped):
        sources = sorted(
            grouped[identity],
            key=lambda item: (
                item[1],
                item[0].issuance_id,
            ),
        )

        census_entries.append(
            ProspectiveValidationFamilyCensusEntry(
                family_key=(
                    family_by_identity[
                        identity
                    ]
                ),
                issuance_count=len(sources),
                issuance_ids=tuple(
                    item[0].issuance_id
                    for item in sources
                ),
                issuance_content_hashes=tuple(
                    item[0].content_hash
                    for item in sources
                ),
                first_issuance_persisted_at=(
                    sources[0][1]
                ),
                last_issuance_persisted_at=(
                    sources[-1][1]
                ),
            )
        )

    census = tuple(
        census_entries
    )

    family_count = len(
        census
    )

    target_identity = _family_identity(
        target_family_key
    )

    target_entry = next(
        (
            entry
            for entry in census
            if _family_identity(
                entry.family_key
            )
            == target_identity
        ),
        None,
    )

    target_present = (
        target_entry is not None
    )

    target_issuance_count = (
        target_entry.issuance_count
        if target_entry is not None
        else 0
    )

    if family_count > 0:
        adjusted_numerator = 1
        adjusted_denominator = (
            20 * family_count
        )
    else:
        adjusted_numerator = None
        adjusted_denominator = None

    anti_selection_guard_passed = (
        audit_scan_complete
        and target_present
    )

    multiplicity_guard_passed = (
        anti_selection_guard_passed
        and family_count > 0
        and adjusted_numerator is not None
        and adjusted_denominator is not None
    )

    validation_input_eligible = (
        multiplicity_guard_passed
    )

    provisional = ProspectiveValidationMultiplicityGuard(
        guard_id="PENDING",
        schema_version=(
            PROSPECTIVE_MULTIPLICITY_GUARD_SCHEMA_V01
        ),
        rules_version=(
            PROSPECTIVE_MULTIPLICITY_GUARD_RULES_V01
        ),

        athlete_id=athlete,
        target_family_key=(
            target_family_key
        ),

        as_of=cutoff,

        audit_scan_complete=(
            audit_scan_complete
        ),

        family_count=family_count,
        target_family_present=(
            target_present
        ),
        target_family_issuance_count=(
            target_issuance_count
        ),

        family_census=census,

        multiplicity_method=(
            ProspectiveMultiplicityMethod
            .BONFERRONI_FWER
        ),

        familywise_alpha_numerator=1,
        familywise_alpha_denominator=20,

        adjusted_alpha_numerator=(
            adjusted_numerator
        ),
        adjusted_alpha_denominator=(
            adjusted_denominator
        ),

        anti_selection_guard_passed=(
            anti_selection_guard_passed
        ),
        multiplicity_guard_passed=(
            multiplicity_guard_passed
        ),

        validation_assessment_input_eligible=(
            validation_input_eligible
        ),

        evidence_level_ceiling=(
            EffectEvidenceLevel.ASSOCIATION_SUPPORTED
        ),
        association_supported=True,

        prospective_validation_established=False,
        causal_attribution_established=False,
        effect_inference_authorized=False,
        readiness_inference_authorized=False,
        performance_prediction_authorized=False,
        prescription_change_authorized=False,
        planning_authorized=False,

        created_at=created,

        content_hash_algorithm=(
            CONTENT_HASH_ALGORITHM
        ),
        content_hash="",
    )

    digest = compute_content_hash(
        provisional,
        exclude_fields=(
            PROSPECTIVE_MULTIPLICITY_GUARD_HASH_EXCLUDE_FIELDS
        ),
    )

    return ProspectiveValidationMultiplicityGuard(
        **{
            **provisional.__dict__,
            "guard_id": (
                "pt-prospective-multiplicity-guard:"
                f"{digest}"
            ),
            "content_hash": digest,
        }
    )
