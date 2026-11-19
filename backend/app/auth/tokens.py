"""Access tokens for built-in accounts.

They use the same claim shape as Supabase tokens (``sub``, ``email``, ``aud``,
``app_metadata.roles``) so every role check works unchanged, plus ``iss=verivote`` and
``ver``, the credential's token version."""

import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt

from app.core.config import Settings
from app.core.errors import AppError
from app.db.enums import Role

ISSUER = "verivote"
AUDIENCE = "authenticated"
_DEV_SECRET_FILE = "auth-secret"


def _dev_secret(settings: Settings) -> str:
    """A per-checkout secret for development, created once and kept under var/."""
    directory = Path(settings.dev_database_path).parent
    path = directory / _DEV_SECRET_FILE
    if path.exists():
        return path.read_text().strip()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    value = secrets.token_urlsafe(48)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(value)
    return value


def signing_secret(settings: Settings) -> str:
    if settings.auth_jwt_secret is not None:
        return settings.auth_jwt_secret.get_secret_value()
    if settings.is_production:
        raise AppError("auth_not_configured", "Authentication is not configured.", 503)
    try:
        return _dev_secret(settings)
    except FileExistsError:
        return _dev_secret(settings)


def issue(
    settings: Settings, user_id: uuid.UUID, email: str, roles: list[Role], version: int
) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.auth_token_minutes)
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(user_id),
        "email": email,
        "app_metadata": {"roles": [role.value for role in roles]},
        "ver": version,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, signing_secret(settings), algorithm="HS256"), expires


def is_local_token(token: str) -> bool:
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return False
    return claims.get("iss") == ISSUER


def decode(token: str, settings: Settings) -> dict[str, object]:
    try:
        return jwt.decode(
            token,
            signing_secret(settings),
            algorithms=["HS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["exp", "sub", "iss", "ver"]},
        )
    except jwt.PyJWTError as exc:
        raise AppError("unauthorized", "Authentication required.", status_code=401) from exc
