from datetime import datetime

from ..domain.evidence.models import EvidenceBundle, create_evidence_bundle
from ..ports.evidence import EvidenceRepository


def collect_available_evidence(
    *,
    repository: EvidenceRepository,
    bundle_id: str,
    athlete_id: str,
    as_of: datetime,
    information_cutoff_at: datetime,
    created_at: datetime,
) -> EvidenceBundle:
    items = repository.list_available(
        athlete_id=athlete_id,
        information_cutoff_at=information_cutoff_at,
    )
    return create_evidence_bundle(
        bundle_id=bundle_id,
        athlete_id=athlete_id,
        as_of=as_of,
        information_cutoff_at=information_cutoff_at,
        created_at=created_at,
        items=items,
    )
