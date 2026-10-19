from typing import Protocol

from ..domain.plan_revision.persistence_contract import (
    AuthoritativePlanIdentity,
    AuthoritativePlanRevision,
    CurrentStateAdoptionBinding,
)


class AuthoritativePlanRevisionRepository(Protocol):
    """P1.1 persistence port; production PostgreSQL implementation is P1.2+.

    Implementations must atomically compare the current revision pointer before
    adoption/append and must never update an existing revision row in place.
    """

    async def get_plan(
        self,
        *,
        logical_plan_id: str,
    ) -> AuthoritativePlanIdentity | None:
        ...

    async def get_plan_for_update(
        self,
        *,
        logical_plan_id: str,
    ) -> AuthoritativePlanIdentity | None:
        ...

    async def get_revision(
        self,
        *,
        revision_id: str,
    ) -> AuthoritativePlanRevision | None:
        ...

    async def get_current_revision(
        self,
        *,
        logical_plan_id: str,
    ) -> AuthoritativePlanRevision | None:
        ...

    async def adopt_current_state(
        self,
        *,
        binding: CurrentStateAdoptionBinding,
        revision: AuthoritativePlanRevision,
    ) -> AuthoritativePlanIdentity:
        ...

    async def append_revision(
        self,
        *,
        expected_current_revision_id: str,
        revision: AuthoritativePlanRevision,
    ) -> AuthoritativePlanIdentity:
        ...
