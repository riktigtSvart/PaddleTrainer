from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.entities import User


async def get_or_create_demo_user(db: AsyncSession) -> User:
    email = get_settings().demo_user_email
    user = await db.scalar(select(User).where(User.email == email))
    if user:
        return user
    user = User(email=email, name="Demo Athlete")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
