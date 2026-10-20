from datetime import datetime

from ..domain.training_state.models import (
    CurrentTrainingState,
    DomainCoverageDeclaration,
    EvidenceCoverage,
    ObservationWindow,
)
from ..domain.training_state.resolver import (
    build_current_training_state,
)
from ..ports.evidence import AsyncEvidenceRepository
from .collect_evidence import (
    collect_available_evidence_async,
)


async def build_current_training_state_from_repository(
    *,
    repository: AsyncEvidenceRepository,
    bundle_id: str,
    state_id: str,
    athlete_id: str,
    schema_version: str,
    as_of: datetime,
    information_cutoff_at: datetime,
    created_at: datetime,
    recent_window: ObservationWindow,
    load_anchor_window: ObservationWindow,
    recent_training_coverage: EvidenceCoverage,
    load_anchor_training_coverage: EvidenceCoverage,
    domain_coverage: tuple[
        DomainCoverageDeclaration,
        ...,
    ] = (),
) -> CurrentTrainingState:
    """Resolve descriptive state from durable cutoff-safe evidence."""

    bundle = await collect_available_evidence_async(
        repository=repository,
        bundle_id=bundle_id,
        athlete_id=athlete_id,
        as_of=as_of,
        information_cutoff_at=information_cutoff_at,
        created_at=created_at,
    )

    return build_current_training_state(
        bundle=bundle,
        state_id=state_id,
        schema_version=schema_version,
        created_at=created_at,
        recent_window=recent_window,
        load_anchor_window=load_anchor_window,
        recent_training_coverage=(
            recent_training_coverage
        ),
        load_anchor_training_coverage=(
            load_anchor_training_coverage
        ),
        domain_coverage=domain_coverage,
    )
