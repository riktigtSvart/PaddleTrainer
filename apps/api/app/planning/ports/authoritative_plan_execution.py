from __future__ import annotations

from typing import Protocol

from ..domain.execution_link import (
    AuthoritativePlanExecutionLink,
)


class AuthoritativePlanExecutionLinkRepository(Protocol):
    async def get_by_session(
        self,
        *,
        workout_session_id: str,
    ) -> AuthoritativePlanExecutionLink | None:
        ...

    async def save(
        self,
        link: AuthoritativePlanExecutionLink,
    ) -> AuthoritativePlanExecutionLink:
        ...
