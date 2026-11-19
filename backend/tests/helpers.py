import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

TEST_SECRET = "test-secret-test-secret-test-secret"

def make_token(
    *,
    roles: list[str] | None = None,
    secret: str = TEST_SECRET,
    user_metadata_roles: list[str] | None = None,
    top_level_role: str | None = None,
    audience: str = "authenticated",
    expired: bool = False,
    subject: str | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject or str(uuid.uuid4()),
        "aud": audience,
        "email": "staff@example.ng",
        "iat": now,
        "exp": now + timedelta(minutes=-5 if expired else 30),
        "app_metadata": {"roles": roles or []},
    }
    if user_metadata_roles is not None:
        payload["user_metadata"] = {"roles": user_metadata_roles}
    if top_level_role is not None:
        payload["role"] = top_level_role
    return jwt.encode(payload, secret, algorithm="HS256")

def unsigned_token() -> str:
    """Craft an alg=none token without asking PyJWT to sign one."""
    header = _b64({"alg": "none", "typ": "JWT"})
    body = _b64(
        {
            "sub": str(uuid.uuid4()),
            "aud": "authenticated",
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
            "app_metadata": {"roles": ["system_admin"]},
        }
    )
    return f"{header}.{body}."

def _b64(value: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()
