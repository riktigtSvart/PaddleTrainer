from datetime import datetime
from typing import Protocol, TypeVar

from ..domain.evidence.models import EvidenceItem


SourceT = TypeVar("SourceT")


class EvidenceSourceAdapter(Protocol[SourceT]):
    """Loss-minimizing boundary from one source record to planning evidence.

    Adapters map only what the source actually establishes. They do not add
    higher-level capability, readiness, fatigue or next-workout conclusions.
    """

    def adapt(
        self,
        source: SourceT,
        *,
        athlete_id: str,
        created_at: datetime,
    ) -> tuple[EvidenceItem, ...]:
        ...


class EvidenceRepository(Protocol):
    def save(self, item: EvidenceItem) -> None:
        ...

    def list_available(
        self,
        *,
        athlete_id: str,
        information_cutoff_at: datetime,
    ) -> tuple[EvidenceItem, ...]:
        ...

class AsyncEvidenceRepository(Protocol):
    """Async durable evidence boundary for production persistence."""

    async def save(
        self,
        item: EvidenceItem,
    ) -> EvidenceItem:
        ...

    async def list_available(
        self,
        *,
        athlete_id: str,
        information_cutoff_at: datetime,
    ) -> tuple[EvidenceItem, ...]:
        ...
