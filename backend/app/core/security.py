import logging
import uuid
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.enums import ADMIN_CONSOLE_ROLES, Role

logger = logging.getLogger("verivote.security")

_bearer = HTTPBearer(auto_error=False)


class Principal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: uuid.UUID
    email: str | None = None
    roles: list[Role]
    must_change_password: bool = False


def _roles_from_app_metadata(payload: dict[str, object]) -> list[Role]:
    """Only app_metadata is authoritative. user_metadata is caller-controlled."""
    app_metadata = payload.get("app_metadata")
    if not isinstance(app_metadata, dict):
        return []
    raw = app_metadata.get("roles")
    if not isinstance(raw, list):
        return []
    roles: list[Role] = []
    for item in raw:
        if isinstance(item, str):
            try:
                roles.append(Role(item))
            except ValueError:
                continue
    return roles


def _decode_local_token(token: str, settings: Settings) -> Principal:
    """Built-in account token. Roles and status are read live, so disabling an account,
    changing its roles or resetting its password takes effect on the next request."""
    from app.auth import service, tokens
    from app.evidence.db import evidence_session_factory

    payload = tokens.decode(token, settings)
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (TypeError, ValueError) as exc:
        raise AppError("unauthorized", "Authentication required.", status_code=401) from exc
    with evidence_session_factory()() as db:
        roles, must_change = service.live_roles(db, user_id, payload.get("ver"))
    email = payload.get("email")
    return Principal(
        user_id=user_id,
        email=email if isinstance(email, str) else None,
        roles=roles,
        must_change_password=must_change,
    )


def decode_access_token(token: str, settings: Settings) -> Principal:
    from app.auth.tokens import is_local_token

    if is_local_token(token):
        return _decode_local_token(token, settings)
    if settings.supabase_jwt_secret is None:
        # Without the secret no Supabase token can be verified, so none is accepted. Answer
        # 401 like any other bad credential: a 503 here would tell unauthenticated callers
        # how the server is configured, and would misreport garbage tokens as an outage.
        logger.warning("rejected a non-built-in token: SUPABASE_JWT_SECRET is not set")
        raise AppError("unauthorized", "Authentication required.", status_code=401)
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience="authenticated",
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise AppError("unauthorized", "Authentication required.", status_code=401) from exc

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (TypeError, ValueError) as exc:
        raise AppError("unauthorized", "Authentication required.", status_code=401) from exc

    email = payload.get("email")
    return Principal(
        user_id=user_id,
        email=email if isinstance(email, str) else None,
        roles=_roles_from_app_metadata(payload),
    )


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AppError("unauthorized", "Authentication required.", status_code=401)
    return decode_access_token(credentials.credentials, settings)


def get_optional_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal | None:
    """For routes open to the public. A token that is present must still be valid."""
    if credentials is None or not credentials.credentials:
        return None
    if credentials.scheme.lower() != "bearer":
        raise AppError("unauthorized", "Authentication required.", status_code=401)
    return decode_access_token(credentials.credentials, settings)


def require_roles(*allowed: Role):
    if not allowed:
        raise ValueError("require_roles needs at least one role")

    def dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if not any(role in allowed for role in principal.roles):
            raise AppError(
                "forbidden",
                "You do not have access to this resource.",
                status_code=403,
            )
        return principal

    return dependency


require_admin = require_roles(*ADMIN_CONSOLE_ROLES)
