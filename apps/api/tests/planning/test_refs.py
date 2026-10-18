from datetime import datetime, timezone

import pytest

from app.planning.domain.common.enums import ProvenanceKind
from app.planning.domain.common.refs import EvidenceRef


def test_naive_available_at_rejected() -> None:
    with pytest.raises(ValueError):
        EvidenceRef(
            evidence_id="e-1",
            evidence_type="PFT_RESPONSE",
            available_at=datetime(2026, 10, 16, 12),
            provenance=ProvenanceKind.SOURCE,
        )


def test_invalid_hash_rejected() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        EvidenceRef(
            evidence_id="e-1",
            evidence_type="PFT_RESPONSE",
            available_at=datetime(
                2026, 10, 16, 12, tzinfo=timezone.utc
            ),
            provenance=ProvenanceKind.SOURCE,
            content_hash="bad",
        )
