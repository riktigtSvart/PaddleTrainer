from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ..domain.common.time import to_utc
from ..domain.persistence.audit import (
    AuditArtifactKind,
)
from ..domain.training_dynamics.prospective_cohort import (
    ProspectiveIssuanceCohortSource,
    ProspectiveOutcomeCohortSource,
    ProspectiveValidationCohort,
    ProspectiveValidationFamilyKey,
    build_prospective_validation_cohort,
)
from ..ports.audit import AsyncPlanningAuditRepository
from .bind_personal_response_prediction_outcome import (
    restore_personal_response_prediction_issuance_audit_artifact,
    restore_personal_response_prediction_outcome_audit_artifact,
)


PROSPECTIVE_COHORT_AUDIT_SCAN_LIMIT = 500


class ProspectiveValidationCohortSourceInvalid(
    RuntimeError
):
    pass


def _uuid_text(
    value: str,
    *,
    field_name: str,
) -> str:
    try:
        parsed = UUID(value)
    except (
        TypeError,
        ValueError,
        AttributeError,
    ) as exc:
        raise ValueError(
            f"{field_name} must be a UUID string."
        ) from exc

    canonical = str(parsed)

    if canonical != value:
        raise ValueError(
            f"{field_name} must be a canonical UUID string."
        )

    return canonical


def _matches_family(
    issuance,
    family_key: ProspectiveValidationFamilyKey,
) -> bool:
    return (
        issuance.model_id
        == family_key.model_id
        and issuance.model_version
        == family_key.model_version
        and issuance.predictor_key
        == family_key.predictor_key
        and issuance.response_key
        == family_key.response_key
    )


async def assemble_prospective_validation_cohort(
    *,
    athlete_id: str,
    family_key: ProspectiveValidationFamilyKey,
    as_of: datetime,
    created_at: datetime,
    audit_repository: AsyncPlanningAuditRepository,
) -> ProspectiveValidationCohort:
    """Assemble all known issued challenges for one exact family.

    list_for_athlete() has a bounded repository limit. Reaching that
    bound means completeness is not proven, so the resulting cohort
    remains explicitly ineligible for later validation assessment.

    Future-persisted audit artifacts are excluded by as_of.
    """

    athlete = _uuid_text(
        athlete_id,
        field_name="athlete_id",
    )

    cutoff = to_utc(
        as_of,
        field_name="as_of",
    )

    issuance_records = (
        await audit_repository.list_for_athlete(
            athlete_id=athlete,
            artifact_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
            ),
            limit=PROSPECTIVE_COHORT_AUDIT_SCAN_LIMIT,
        )
    )

    outcome_records = (
        await audit_repository.list_for_athlete(
            athlete_id=athlete,
            artifact_kind=(
                AuditArtifactKind
                .PERSONAL_RESPONSE_PREDICTION_OUTCOME
            ),
            limit=PROSPECTIVE_COHORT_AUDIT_SCAN_LIMIT,
        )
    )

    audit_scan_complete = (
        len(issuance_records)
        < PROSPECTIVE_COHORT_AUDIT_SCAN_LIMIT
        and len(outcome_records)
        < PROSPECTIVE_COHORT_AUDIT_SCAN_LIMIT
    )

    all_issuances = {}
    target_issuance_sources = []

    for record in issuance_records:
        if record.athlete_id != athlete:
            raise ProspectiveValidationCohortSourceInvalid(
                "Audit repository returned cross-athlete issuance."
            )

        if record.persisted_at is None:
            raise ProspectiveValidationCohortSourceInvalid(
                "Prediction issuance has no database "
                "persistence timestamp."
            )

        persisted = to_utc(
            record.persisted_at,
            field_name="issuance_record.persisted_at",
        )

        if persisted > cutoff:
            continue

        issuance = (
            restore_personal_response_prediction_issuance_audit_artifact(
                record
            )
        )

        if issuance.issuance_id in all_issuances:
            raise ProspectiveValidationCohortSourceInvalid(
                "Duplicate issuance artifact identity returned "
                "by audit repository."
            )

        all_issuances[
            issuance.issuance_id
        ] = (
            issuance,
            persisted,
        )

        if _matches_family(
            issuance,
            family_key,
        ):
            target_issuance_sources.append(
                ProspectiveIssuanceCohortSource(
                    issuance=issuance,
                    persisted_at=persisted,
                )
            )

    target_ids = {
        source.issuance.issuance_id
        for source in target_issuance_sources
    }

    target_outcomes = []

    for record in outcome_records:
        if record.athlete_id != athlete:
            raise ProspectiveValidationCohortSourceInvalid(
                "Audit repository returned cross-athlete outcome."
            )

        if record.persisted_at is None:
            raise ProspectiveValidationCohortSourceInvalid(
                "Prospective outcome has no database "
                "persistence timestamp."
            )

        persisted = to_utc(
            record.persisted_at,
            field_name="outcome_record.persisted_at",
        )

        if persisted > cutoff:
            continue

        challenge = (
            restore_personal_response_prediction_outcome_audit_artifact(
                record
            )
        )

        source_issuance = all_issuances.get(
            challenge.source_issuance_id
        )

        if source_issuance is None:
            if audit_scan_complete:
                raise ProspectiveValidationCohortSourceInvalid(
                    "Prospective outcome references an issuance "
                    "missing from the complete audit scan."
                )

            # The bounded scan may have omitted the issuance.
            # Keep the cohort explicitly incomplete rather than
            # guessing its family.
            continue

        if challenge.source_issuance_id not in target_ids:
            continue

        target_outcomes.append(
            ProspectiveOutcomeCohortSource(
                challenge=challenge,
                persisted_at=persisted,
            )
        )

    return build_prospective_validation_cohort(
        athlete_id=athlete,
        family_key=family_key,
        as_of=cutoff,
        issuance_sources=tuple(
            target_issuance_sources
        ),
        outcome_sources=tuple(
            target_outcomes
        ),
        audit_scan_complete=(
            audit_scan_complete
        ),
        created_at=created_at,
    )
