import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth import service, tokens
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import SlidingWindowLimiter, client_key
from app.core.security import Principal, get_current_principal, require_admin, require_roles
from app.db.enums import Role
from app.evidence.db import get_evidence_db

router = APIRouter(prefix="/auth", tags=["auth"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])

Db = Annotated[Session, Depends(get_evidence_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
SystemAdmin = Annotated[Principal, Depends(require_roles(Role.SYSTEM_ADMIN))]
CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]

# Per client address, on top of the per-account lockout.
_sign_in_limiter = SlidingWindowLimiter(limit=20, window_seconds=15 * 60)


class SignInIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str | None
    roles: list[Role]
    is_active: bool
    has_password: bool
    must_change_password: bool
    last_sign_in_at: datetime | None
    created_at: datetime | None


class SessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    account: AccountOut


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class CreateAccountIn(BaseModel):
    email: EmailStr
    display_name: str | None = Field(default=None, max_length=200)
    roles: list[Role] = Field(min_length=1, max_length=len(Role))
    # Leave empty to generate a temporary password that must be changed at first sign-in.
    password: str | None = Field(default=None, max_length=256)


class UpdateAccountIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    roles: list[Role] | None = Field(default=None, max_length=len(Role))
    is_active: bool | None = None


class CreatedAccountOut(BaseModel):
    account: AccountOut
    temporary_password: str | None


class TemporaryPasswordOut(BaseModel):
    temporary_password: str


def _out(account: service.Account) -> AccountOut:
    credential = account.credential
    return AccountOut(
        id=account.user.id,
        email=account.user.email,
        display_name=account.user.display_name,
        roles=account.roles,
        is_active=account.user.is_active,
        has_password=credential is not None,
        must_change_password=bool(credential and credential.must_change_password),
        last_sign_in_at=credential.last_sign_in_at if credential else None,
        created_at=account.user.created_at,
    )


def _session(settings: Settings, account: service.Account) -> SessionOut:
    assert account.credential is not None
    roles = [] if account.credential.must_change_password else account.roles
    token, expires = tokens.issue(
        settings, account.user.id, account.user.email, roles, account.credential.token_version
    )
    return SessionOut(access_token=token, expires_at=expires, account=_out(account))


@router.post("/login", response_model=SessionOut)
def sign_in(request: Request, body: SignInIn, db: Db, settings: AppSettings) -> SessionOut:
    allowed, retry_after = _sign_in_limiter.check(client_key(request, settings.trust_proxy_headers))
    if not allowed:
        raise AppError(
            "rate_limited",
            f"Too many sign-in attempts. Try again in {max(1, retry_after // 60)} minute(s).",
            429,
        )
    account = service.authenticate(db, settings, body.email, body.password)
    return _session(settings, account)


@router.get("/me", response_model=Principal)
def read_current_principal(principal: CurrentPrincipal) -> Principal:
    return principal


@router.get("/account", response_model=AccountOut)
def read_own_account(principal: CurrentPrincipal, db: Db) -> AccountOut:
    return _out(service.get_account(db, principal.user_id))


@router.post("/password", response_model=SessionOut)
def change_own_password(
    body: ChangePasswordIn, principal: CurrentPrincipal, db: Db, settings: AppSettings
) -> SessionOut:
    """Change the signed-in user's password. Other sessions end; a fresh token is returned."""
    account = service.change_password(
        db, principal.user_id, body.current_password, body.new_password
    )
    return _session(settings, account)


@admin_router.get("/session", response_model=Principal)
def read_admin_session(
    principal: Annotated[Principal, Depends(require_admin)],
) -> Principal:
    """Confirms an administrative session. It does not expose operational data."""
    return principal


@admin_router.get("/users", response_model=list[AccountOut])
def list_users(_: SystemAdmin, db: Db) -> list[AccountOut]:
    return [_out(account) for account in service.list_accounts(db)]


@admin_router.post("/users", response_model=CreatedAccountOut, status_code=201)
def create_user(body: CreateAccountIn, admin: SystemAdmin, db: Db) -> CreatedAccountOut:
    account, temporary = service.create_account(
        db,
        email=str(body.email),
        display_name=body.display_name,
        roles=body.roles,
        password=body.password or None,
        actor=admin.user_id,
    )
    return CreatedAccountOut(account=_out(account), temporary_password=temporary)


@admin_router.patch("/users/{user_id}", response_model=AccountOut)
def update_user(
    user_id: uuid.UUID, body: UpdateAccountIn, admin: SystemAdmin, db: Db
) -> AccountOut:
    account = service.update_account(
        db,
        user_id,
        actor=admin.user_id,
        roles=body.roles,
        is_active=body.is_active,
        display_name=body.display_name,
    )
    return _out(account)


@admin_router.post("/users/{user_id}/password-reset", response_model=TemporaryPasswordOut)
def reset_user_password(user_id: uuid.UUID, admin: SystemAdmin, db: Db) -> TemporaryPasswordOut:
    if user_id == admin.user_id:
        raise AppError(
            "use_change_password", "Change your own password from your account page.", 409
        )
    return TemporaryPasswordOut(
        temporary_password=service.reset_password(db, user_id, admin.user_id)
    )
