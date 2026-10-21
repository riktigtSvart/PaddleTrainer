from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc
from .association_dataset import (
    PersonalAssociationPredictorKey,
)
from .models import EffectEvidenceLevel
from .prospective_issuance import (
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01,
    PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01,
    PersonalResponsePredictionIssuanceContract,
)
from .prospective_outcome import (
    PROSPECTIVE_RESPONSE_CHALLENGE_RULES_V01,
    PROSPECTIVE_RESPONSE_CHALLENGE_SCHEMA_V01,
    ProspectiveResponseChallenge,
    ProspectiveResponseChallengeResult,
)
from .response_reference import ResponseMetricReferenceKey


PROSPECTIVE_VALIDATION_COHORT_SCHEMA_V01 = (
    "prospective-validation-cohort-v0.1"
)

PROSPECTIVE_VALIDATION_COHORT_RULES_V01 = (
    "prospective-validation-cohort-rules-v0.1"
)

PROSPECTIVE_VALIDATION_COHORT_HASH_EXCLUDE_FIELDS = (
    frozenset(
        {
            "cohort_id",
            "created_at",
            "content_hash",
        }
    )
)


class ProspectiveCohortOutcomeStatus(StrEnum):
    UNBOUND = "unbound"
    DIRECTION_MATCHED = "direction_matched"
    DIRECTION_MISMATCHED = "direction_mismatched"
    TIED_UNSCORABLE = "tied_unscorable"


@dataclass(frozen=True)
class ProspectiveValidationFamilyKey:
    model_id: str
    model_version: str
    predictor_key: PersonalAssociationPredictorKey
    response_key: ResponseMetricReferenceKey


@dataclass(frozen=True)
class ProspectiveIssuanceCohortSource:
    issuance: PersonalResponsePredictionIssuanceContract
    persisted_at: datetime


@dataclass(frozen=True)
class ProspectiveOutcomeCohortSource:
    challenge: ProspectiveResponseChallenge
    persisted_at: datetime


@dataclass(frozen=True)
class ProspectiveChallengeCohortEntry:
    issuance_id: str
    issuance_content_hash: str
    workout_session_id: str
    issuance_persisted_at: datetime

    duplicate_session_issuance: bool

    outcome_status: ProspectiveCohortOutcomeStatus

    binding_id: str | None
    binding_content_hash: str | None
    binding_persisted_at: datetime | None

    response_artifact_id: str | None
    response_artifact_content_hash: str | None

    directional_score_available: bool


@dataclass(frozen=True)
class ProspectiveValidationCohort:
    """Complete-as-known prospective challenge cohort for one exact family.

    The cohort deliberately retains:
    - unbound issuances,
    - tied/unscorable outcomes,
    - duplicate same-session issuances.

    C1 does not perform or authorize prospective validation.
    """

    cohort_id: str
    schema_version: str
    rules_version: str

    athlete_id: str
    family_key: ProspectiveValidationFamilyKey

    as_of: datetime

    audit_scan_complete: bool

    issued_challenge_count: int
    bound_challenge_count: int
    directionally_scored_count: int

    matched_count: int
    mismatched_count: int
    tied_unscorable_count: int
    unbound_count: int

    duplicate_session_count: int
    duplicate_issuance_count: int

    selection_guard_passed: bool
    outcome_completeness_established: bool
    validation_assessment_input_eligible: bool

    entries: tuple[
        ProspectiveChallengeCohortEntry,
        ...,
    ]

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
                    PROSPECTIVE_VALIDATION_COHORT_HASH_EXCLUDE_FIELDS
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


def _matches_family(
    issuance: PersonalResponsePredictionIssuanceContract,
    family: ProspectiveValidationFamilyKey,
) -> bool:
    return (
        issuance.model_id == family.model_id
        and issuance.model_version
        == family.model_version
        and issuance.predictor_key
        == family.predictor_key
        and issuance.response_key
        == family.response_key
    )


def _validate_issuance(
    *,
    source: ProspectiveIssuanceCohortSource,
    athlete_id: str,
    family: ProspectiveValidationFamilyKey,
    as_of: datetime,
) -> datetime:
    issuance = source.issuance

    if not issuance.verify_content_hash():
        raise ValueError(
            "Prospective cohort issuance content hash "
            "does not verify."
        )

    if (
        issuance.schema_version
        != PERSONAL_RESPONSE_PREDICTION_ISSUANCE_SCHEMA_V01
        or issuance.rules_version
        != PERSONAL_RESPONSE_PREDICTION_ISSUANCE_RULES_V01
    ):
        raise ValueError(
            "Unsupported prospective cohort issuance."
        )

    if issuance.athlete_id != athlete_id:
        raise ValueError(
            "Prospective cohort issuance athlete differs."
        )

    if not _matches_family(
        issuance,
        family,
    ):
        raise ValueError(
            "Prospective cohort issuance belongs to a "
            "different validation family."
        )

    if (
        issuance.response_prediction_available is not True
        or issuance.evidence_level_ceiling
        != EffectEvidenceLevel.ASSOCIATION_SUPPORTED
        or issuance.association_supported is not True
    ):
        raise ValueError(
            "Prospective cohort issuance lacks required "
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
            "Prospective cohort issuance contains "
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

    cutoff_at = to_utc(
        issuance.information_cutoff_at,
        field_name="issuance.information_cutoff_at",
    )

    if persisted < prediction_at:
        raise ValueError(
            "Issuance persistence predates prediction_at."
        )

    if persisted < cutoff_at:
        raise ValueError(
            "Issuance persistence predates information cutoff."
        )

    if persisted > as_of:
        raise ValueError(
            "Prospective cohort contains future issuance."
        )

    return persisted


def _validate_outcome(
    *,
    source: ProspectiveOutcomeCohortSource,
    issuance_source: ProspectiveIssuanceCohortSource,
    issuance_persisted_at: datetime,
    athlete_id: str,
    as_of: datetime,
) -> datetime:
    challenge = source.challenge
    issuance = issuance_source.issuance

    if not challenge.verify_content_hash():
        raise ValueError(
            "Prospective cohort outcome content hash "
            "does not verify."
        )

    if (
        challenge.schema_version
        != PROSPECTIVE_RESPONSE_CHALLENGE_SCHEMA_V01
        or challenge.rules_version
        != PROSPECTIVE_RESPONSE_CHALLENGE_RULES_V01
    ):
        raise ValueError(
            "Unsupported prospective cohort outcome."
        )

    if (
        challenge.athlete_id != athlete_id
        or challenge.workout_session_id
        != issuance.workout_session_id
    ):
        raise ValueError(
            "Prospective outcome identity does not match "
            "its issuance."
        )

    if (
        challenge.source_issuance_id
        != issuance.issuance_id
        or challenge.source_issuance_content_hash
        != issuance.content_hash
    ):
        raise ValueError(
            "Prospective outcome does not hash-bind "
            "its issuance."
        )

    if (
        challenge.source_candidate_id
        != issuance.source_candidate_id
        or challenge.source_candidate_content_hash
        != issuance.source_candidate_content_hash
        or challenge.response_key
        != issuance.response_key
        or challenge.prediction_direction
        != issuance.predicted_response_direction
        or challenge.historical_response_median
        != float(
            issuance.historical_response_median
        )
    ):
        raise ValueError(
            "Prospective outcome does not replay the "
            "issued prediction."
        )

    if (
        challenge.issuance_persisted_at
        != issuance_persisted_at
    ):
        raise ValueError(
            "Prospective outcome records a different "
            "issuance persistence boundary."
        )

    if (
        challenge.prospective_challenge_established
        is not True
        or challenge.evidence_level_ceiling
        != EffectEvidenceLevel.ASSOCIATION_SUPPORTED
        or challenge.association_supported is not True
    ):
        raise ValueError(
            "Prospective outcome lacks bounded "
            "challenge authority."
        )

    if any(
        (
            challenge.prospective_validation_established,
            challenge.causal_attribution_established,
            challenge.effect_inference_authorized,
            challenge.readiness_inference_authorized,
            challenge.performance_prediction_authorized,
            challenge.prescription_change_authorized,
            challenge.planning_authorized,
        )
    ):
        raise ValueError(
            "Prospective outcome contains unsupported "
            "stronger authority."
        )

    persisted = to_utc(
        source.persisted_at,
        field_name="outcome.persisted_at",
    )

    if persisted < challenge.response_persisted_at:
        raise ValueError(
            "Outcome binding persistence predates "
            "response persistence."
        )

    if persisted > as_of:
        raise ValueError(
            "Prospective cohort contains future outcome."
        )

    return persisted


def build_prospective_validation_cohort(
    *,
    athlete_id: str,
    family_key: ProspectiveValidationFamilyKey,
    as_of: datetime,
    issuance_sources: tuple[
        ProspectiveIssuanceCohortSource,
        ...,
    ],
    outcome_sources: tuple[
        ProspectiveOutcomeCohortSource,
        ...,
    ],
    audit_scan_complete: bool,
    created_at: datetime,
) -> ProspectiveValidationCohort:
    """Build one deterministic, non-selective prospective cohort."""

    athlete = _require_non_empty(
        athlete_id,
        field_name="athlete_id",
    )

    _validate_family(
        family_key
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
            "Prospective cohort cannot be created "
            "before as_of."
        )

    if not isinstance(
        audit_scan_complete,
        bool,
    ):
        raise ValueError(
            "audit_scan_complete must be boolean."
        )

    issuance_by_id = {}
    persisted_by_id = {}

    for source in issuance_sources:
        issuance = source.issuance

        if issuance.issuance_id in issuance_by_id:
            raise ValueError(
                "Duplicate issuance artifact identity "
                "in cohort source."
            )

        persisted = _validate_issuance(
            source=source,
            athlete_id=athlete,
            family=family_key,
            as_of=cutoff,
        )

        issuance_by_id[
            issuance.issuance_id
        ] = source

        persisted_by_id[
            issuance.issuance_id
        ] = persisted

    outcome_by_issuance = {}
    outcome_persisted_by_issuance = {}

    for source in outcome_sources:
        challenge = source.challenge

        issuance_source = issuance_by_id.get(
            challenge.source_issuance_id
        )

        if issuance_source is None:
            raise ValueError(
                "Prospective outcome references issuance "
                "outside the cohort source."
            )

        if (
            challenge.source_issuance_id
            in outcome_by_issuance
        ):
            raise ValueError(
                "Multiple outcome bindings reference "
                "the same issuance."
            )

        persisted = _validate_outcome(
            source=source,
            issuance_source=issuance_source,
            issuance_persisted_at=(
                persisted_by_id[
                    challenge.source_issuance_id
                ]
            ),
            athlete_id=athlete,
            as_of=cutoff,
        )

        outcome_by_issuance[
            challenge.source_issuance_id
        ] = source

        outcome_persisted_by_issuance[
            challenge.source_issuance_id
        ] = persisted

    session_counts = Counter(
        source.issuance.workout_session_id
        for source in issuance_sources
    )

    entries = []

    matched_count = 0
    mismatched_count = 0
    tied_count = 0
    unbound_count = 0

    for source in issuance_sources:
        issuance = source.issuance
        outcome_source = outcome_by_issuance.get(
            issuance.issuance_id
        )

        duplicate = (
            session_counts[
                issuance.workout_session_id
            ]
            > 1
        )

        if outcome_source is None:
            unbound_count += 1

            outcome_status = (
                ProspectiveCohortOutcomeStatus.UNBOUND
            )

            binding_id = None
            binding_hash = None
            binding_persisted_at = None
            response_id = None
            response_hash = None
            directional_score_available = False

        else:
            challenge = outcome_source.challenge

            binding_id = challenge.binding_id
            binding_hash = challenge.content_hash
            binding_persisted_at = (
                outcome_persisted_by_issuance[
                    issuance.issuance_id
                ]
            )
            response_id = (
                challenge.source_response_artifact_id
            )
            response_hash = (
                challenge.source_response_content_hash
            )
            directional_score_available = (
                challenge.directional_score_available
            )

            if (
                challenge.result
                == ProspectiveResponseChallengeResult
                .DIRECTION_MATCHED
            ):
                matched_count += 1
                outcome_status = (
                    ProspectiveCohortOutcomeStatus
                    .DIRECTION_MATCHED
                )

            elif (
                challenge.result
                == ProspectiveResponseChallengeResult
                .DIRECTION_MISMATCHED
            ):
                mismatched_count += 1
                outcome_status = (
                    ProspectiveCohortOutcomeStatus
                    .DIRECTION_MISMATCHED
                )

            elif (
                challenge.result
                == ProspectiveResponseChallengeResult
                .TIED_UNSCORABLE
            ):
                tied_count += 1
                outcome_status = (
                    ProspectiveCohortOutcomeStatus
                    .TIED_UNSCORABLE
                )

            else:
                raise ValueError(
                    "Unsupported prospective challenge result."
                )

        entries.append(
            ProspectiveChallengeCohortEntry(
                issuance_id=issuance.issuance_id,
                issuance_content_hash=(
                    issuance.content_hash
                ),
                workout_session_id=(
                    issuance.workout_session_id
                ),
                issuance_persisted_at=(
                    persisted_by_id[
                        issuance.issuance_id
                    ]
                ),

                duplicate_session_issuance=(
                    duplicate
                ),

                outcome_status=outcome_status,

                binding_id=binding_id,
                binding_content_hash=binding_hash,
                binding_persisted_at=(
                    binding_persisted_at
                ),

                response_artifact_id=response_id,
                response_artifact_content_hash=(
                    response_hash
                ),

                directional_score_available=(
                    directional_score_available
                ),
            )
        )

    ordered_entries = tuple(
        sorted(
            entries,
            key=lambda item: (
                item.issuance_persisted_at,
                item.issuance_id,
            ),
        )
    )

    issued_count = len(ordered_entries)
    bound_count = issued_count - unbound_count

    scored_count = (
        matched_count
        + mismatched_count
    )

    duplicate_sessions = tuple(
        session_id
        for session_id, count
        in session_counts.items()
        if count > 1
    )

    duplicate_session_count = len(
        duplicate_sessions
    )

    duplicate_issuance_count = sum(
        count - 1
        for count in session_counts.values()
        if count > 1
    )

    selection_guard_passed = (
        audit_scan_complete
        and duplicate_session_count == 0
    )

    outcome_completeness_established = (
        unbound_count == 0
    )

    validation_input_eligible = (
        issued_count > 0
        and selection_guard_passed
        and outcome_completeness_established
    )

    provisional = ProspectiveValidationCohort(
        cohort_id="PENDING",
        schema_version=(
            PROSPECTIVE_VALIDATION_COHORT_SCHEMA_V01
        ),
        rules_version=(
            PROSPECTIVE_VALIDATION_COHORT_RULES_V01
        ),

        athlete_id=athlete,
        family_key=family_key,

        as_of=cutoff,

        audit_scan_complete=(
            audit_scan_complete
        ),

        issued_challenge_count=issued_count,
        bound_challenge_count=bound_count,
        directionally_scored_count=scored_count,

        matched_count=matched_count,
        mismatched_count=mismatched_count,
        tied_unscorable_count=tied_count,
        unbound_count=unbound_count,

        duplicate_session_count=(
            duplicate_session_count
        ),
        duplicate_issuance_count=(
            duplicate_issuance_count
        ),

        selection_guard_passed=(
            selection_guard_passed
        ),
        outcome_completeness_established=(
            outcome_completeness_established
        ),
        validation_assessment_input_eligible=(
            validation_input_eligible
        ),

        entries=ordered_entries,

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
            PROSPECTIVE_VALIDATION_COHORT_HASH_EXCLUDE_FIELDS
        ),
    )

    return ProspectiveValidationCohort(
        **{
            **provisional.__dict__,
            "cohort_id": (
                "pt-prospective-validation-cohort:"
                f"{digest}"
            ),
            "content_hash": digest,
        }
    )
