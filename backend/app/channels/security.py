"""Gateway callback checks and telephone-number hashing.

A gateway proves a callback came from it by signing the raw request body with the
shared webhook secret: header `X-VoteTrace-Signature: sha256=<hex HMAC-SHA256>`. The
simulator accepts unsigned requests, and only while simulator mode is on."""

import hashlib
import hmac
import re
import secrets
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr

from app.core.config import Settings
from app.core.errors import AppError

SIGNATURE_HEADER = "X-VoteTrace-Signature"
_PHONE = re.compile(r"^\+?\d{7,15}$")

Origin = Literal["gateway", "simulator"]


@lru_cache
def _process_secret() -> bytes:
    # Development fallback only: hashes change on every restart, which is acceptable
    # for a simulator. Production requires CHANNEL_HASH_SECRET.
    return secrets.token_bytes(32)


def normalise_phone(value: str) -> str:
    cleaned = re.sub(r"[\s().-]", "", value)
    if not _PHONE.fullmatch(cleaned):
        raise AppError("invalid_phone_number", "The telephone number is not valid.", 422)
    if cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = "+234" + cleaned[1:]
    return cleaned if cleaned.startswith("+") else "+" + cleaned


def hash_phone(settings: Settings, phone: str) -> str:
    """Keyed hash of a number. Lets us rate-limit and spot repeats without storing it."""
    key = (
        settings.channel_hash_secret.get_secret_value().encode()
        if settings.channel_hash_secret
        else _process_secret()
    )
    return hmac.new(key, normalise_phone(phone).encode(), hashlib.sha256).hexdigest()


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_callback_token(settings: Settings, token: str | None) -> bool:
    """True when the request carries the configured callback token. Raises if a token is
    present but wrong, so a misconfigured gateway fails loudly instead of being treated
    as simulator traffic."""
    if not token:
        return False
    expected = settings.channel_callback_token
    if expected is None or not hmac.compare_digest(
        expected.get_secret_value().encode(), token.encode()
    ):
        raise AppError("unauthorized", "The gateway callback token is not valid.", 401)
    return True


def verify_origin(
    settings: Settings,
    secret: SecretStr | None,
    body: bytes,
    signature: str | None,
    token: str | None = None,
) -> Origin:
    """Decide whether a callback is an authenticated gateway call or a simulator call.

    A gateway proves origin either by signing the body (HMAC) or, for providers that
    cannot sign, by the secret callback token in the URL."""
    if verify_callback_token(settings, token):
        return "gateway"
    if signature:
        if secret is None:
            raise AppError("unauthorized", "Gateway signatures are not configured.", 401)
        expected = sign(secret.get_secret_value(), body)
        if not hmac.compare_digest(expected, signature.strip()):
            raise AppError("unauthorized", "The gateway signature is not valid.", 401)
        return "gateway"
    if settings.simulator_enabled:
        return "simulator"
    if secret is not None or settings.channel_callback_token is not None:
        raise AppError("unauthorized", "A gateway signature or callback token is required.", 401)
    raise AppError("channel_unavailable", "This channel is not configured.", 503)


def require_simulator(settings: Settings) -> None:
    if not settings.simulator_enabled:
        raise AppError("simulator_disabled", "The channel simulator is turned off.", 404)
