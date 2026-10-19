from __future__ import annotations

from typing import Protocol

from ..domain.occurrence_execution import (
    AuthoritativeOccurrenceExecutionLink,
)


class AuthoritativeOccurrenceExecutionLinkRepository(Protocol):
    async def get_by_occurrence(
        self,
        *,
        plan_execution_link_id: str,
        authoritative_occurrence_id: str,
    ) -> AuthoritativeOccurrenceExecutionLink | None:
        ...

    async def save(
        self,
        link: AuthoritativeOccurrenceExecutionLink,
    ) -> AuthoritativeOccurrenceExecutionLink:
        ...
