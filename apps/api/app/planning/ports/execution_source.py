from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LockedExecutionSourceCapture:
    session_snapshot: dict
    source_workout_snapshot: dict
    source_workout_content_hash: str
    session_source_content_hash: str


class ExecutionSourceNotFound(LookupError):
    pass


class LockedExecutionSourceProvider(Protocol):
    async def lock_and_capture(
        self,
        session,
        *,
        athlete_id: str,
        source_workout_id: str,
        workout_session_id: str,
    ) -> LockedExecutionSourceCapture:
        ...
