from __future__ import annotations

from typing import Protocol

from ..domain.response_evidence.source_capture import (
    TrainingResponseSourceCapture,
)


class LockedTrainingResponseSourceProvider(Protocol):
    """Lock and capture one explicitly session-linked response source."""

    async def lock_and_capture(
        self,
        session,
        *,
        athlete_id: str,
        response_source_id: str,
    ) -> TrainingResponseSourceCapture:
        ...
