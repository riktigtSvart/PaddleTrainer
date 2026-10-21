from __future__ import annotations

from datetime import datetime

from ..domain.training_dynamics.prospective_cohort import (
    ProspectiveValidationFamilyKey,
)
from ..domain.training_dynamics.prospective_validation import (
    build_prospective_validation_assessment,
)
from ..domain.training_dynamics.prospective_validation_evidence import (
    ProspectiveValidationEvidence,
    build_prospective_validation_evidence,
)
from ..ports.audit import AsyncPlanningAuditRepository
from .assemble_prospective_multiplicity_guard import (
    assemble_prospective_validation_multiplicity_guard,
)
from .assemble_prospective_validation_cohort import (
    assemble_prospective_validation_cohort,
)


async def assemble_prospective_validation_evidence(
    *,
    athlete_id: str,
    family_key: ProspectiveValidationFamilyKey,
    as_of: datetime,
    created_at: datetime,
    audit_repository: AsyncPlanningAuditRepository,
) -> ProspectiveValidationEvidence:
    """Replay durable C1+C2+C3 lineage and materialize P2.3D evidence."""

    cohort = await assemble_prospective_validation_cohort(
        athlete_id=athlete_id,
        family_key=family_key,
        as_of=as_of,
        created_at=created_at,
        audit_repository=audit_repository,
    )

    multiplicity_guard = await (
        assemble_prospective_validation_multiplicity_guard(
            athlete_id=athlete_id,
            target_family_key=family_key,
            as_of=as_of,
            created_at=created_at,
            audit_repository=audit_repository,
        )
    )

    assessment = build_prospective_validation_assessment(
        cohort=cohort,
        multiplicity_guard=multiplicity_guard,
        created_at=created_at,
    )

    return build_prospective_validation_evidence(
        cohort=cohort,
        multiplicity_guard=multiplicity_guard,
        assessment=assessment,
        created_at=created_at,
    )
