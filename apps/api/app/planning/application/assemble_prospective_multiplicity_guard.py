from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ..domain.common.time import to_utc
from ..domain.persistence.audit import (
    AuditArtifactKind,
)
from ..domain.training_dynamics.prospective_cohort import (
    ProspectiveIssuanceCohortSource,
    ProspectiveValidationFamilyKey,
)
from ..domain.training_dynamics.prospective_multiplicity import (
    ProspectiveValidationMultiplicityGuard,
    build_prospective_validation_multiplicity_guard,
)
from ..ports.audit import AsyncPlanningAuditRepository
from .bind_personal_response_prediction_outcome import (
    restore_personal_response_prediction_issuance_audit_artifact,
)


PROSPECTIVE_MULTIPLICITY_AUDIT_SCAN_LIMIT = 500


class ProspectiveMultiplicitySourceInvalid(
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


async def assemble_prospective_validation_multiplicity_guard(
    *,
    athlete_id: str,
    target_family_key: ProspectiveValidationFamilyKey,
    as_of: datetime,
    created_at: datetime,
    audit_repository: AsyncPlanningAuditRepository,
) -> ProspectiveValidationMultiplicityGuard:
    """Assemble the outcome-independent prospective hypothesis census.

    Every durable issuance at or before `as_of` contributes its exact
    validation family.

    Reaching the repository scan limit means completeness is unknown and
    therefore the multiplicity guard fails closed.
    """

    athlete = _uuid_text(
        athlete_id,
        field_name="athlete_id",
    )

    cutoff = to_utc(
        as_of,
        field_name="as_of",
    )

    records = await audit_repository.list_for_athlete(
        athlete_id=athlete,
        artifact_kind=(
            AuditArtifactKind
            .PERSONAL_RESPONSE_PREDICTION_ISSUANCE
        ),
        limit=(
            PROSPECTIVE_MULTIPLICITY_AUDIT_SCAN_LIMIT
        ),
    )

    audit_scan_complete = (
        len(records)
        < PROSPECTIVE_MULTIPLICITY_AUDIT_SCAN_LIMIT
    )

    sources = []

    for record in records:
        if record.athlete_id != athlete:
            raise ProspectiveMultiplicitySourceInvalid(
                "Audit repository returned cross-athlete issuance."
            )

        if record.persisted_at is None:
            raise ProspectiveMultiplicitySourceInvalid(
                "Prediction issuance has no database "
                "persistence timestamp."
            )

        persisted = to_utc(
            record.persisted_at,
            field_name="record.persisted_at",
        )

        if persisted > cutoff:
            continue

        issuance = (
            restore_personal_response_prediction_issuance_audit_artifact(
                record
            )
        )

        sources.append(
            ProspectiveIssuanceCohortSource(
                issuance=issuance,
                persisted_at=persisted,
            )
        )

    return build_prospective_validation_multiplicity_guard(
        athlete_id=athlete,
        target_family_key=target_family_key,
        as_of=cutoff,
        issuance_sources=tuple(
            sources
        ),
        audit_scan_complete=(
            audit_scan_complete
        ),
        created_at=created_at,
    )
