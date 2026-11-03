"""Restart-safe review polling; immutable input keys coalesce duplicate events."""

import asyncio
import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import User
from app.services.training_plans import refresh_active

logger = logging.getLogger(__name__)
INTERVAL_SECONDS = 60


async def run_once(session_factory=SessionLocal):
    async with session_factory() as session:
        owner = (
            await session.execute(
                select(User.id).where(User.email == get_settings().demo_user_email)
            )
        ).scalar_one_or_none()
        await session.rollback()
        if owner is not None:
            return await refresh_active(session, str(owner))
        return []


async def monitor():
    while True:
        try:
            await run_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            # A transient failure must not kill future reviews or report an
            # unsaved suggestion as completed. The next tick retries the DB.
            logger.exception("Training plan review failed; retrying on next tick")
        await asyncio.sleep(INTERVAL_SECONDS)
