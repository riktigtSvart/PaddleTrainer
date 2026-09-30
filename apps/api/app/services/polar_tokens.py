from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret, encrypt_secret
from app.integrations.polar.client import PolarClient
from app.models.entities import ExternalConnection


async def get_valid_access_token(db: AsyncSession, connection: ExternalConnection) -> str:
    now = datetime.now(timezone.utc)
    expires_at = connection.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    access_token = decrypt_secret(connection.access_token_encrypted)
    if not access_token:
        raise RuntimeError("Polar access token missing")

    # Refresh a little early to avoid expiry during a longer sync request.
    if expires_at > now + timedelta(minutes=2):
        return access_token

    refresh_token = decrypt_secret(connection.refresh_token_encrypted)
    if not refresh_token:
        raise RuntimeError("Polar refresh token missing; reconnect Polar account")

    token = await PolarClient().refresh_token(refresh_token)
    connection.access_token_encrypted = encrypt_secret(token["access_token"])
    if token.get("refresh_token"):
        connection.refresh_token_encrypted = encrypt_secret(token["refresh_token"])
    connection.expires_at = now + timedelta(seconds=int(token.get("expires_in", 43199)))
    connection.scopes = token.get("scope", "").split() or connection.scopes
    connection.updated_at = now
    await db.commit()
    return token["access_token"]
