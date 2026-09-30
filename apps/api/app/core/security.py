import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    if settings.token_encryption_key:
        key = settings.token_encryption_key.encode()
    else:
        # Development-only deterministic fallback. Configure TOKEN_ENCRYPTION_KEY in production.
        digest = hashlib.sha256(b"paddle-coach-dev-key").digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str | None) -> str | None:
    if value is None:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    if value is None:
        return None
    return _fernet().decrypt(value.encode()).decode()
