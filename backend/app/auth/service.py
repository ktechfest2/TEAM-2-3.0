"""Built-in account rules: sign-in, live token checks and account management."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import passwords
from app.core.config import Settings
from app.core.errors import AppError
from app.db.enums import Role
from app.db.models import RoleAssignment, User, UserCredential
from app.evidence.audit import append_event

ENTITY_ACCOUNT = "account"

_SIGN_IN_FAILED = "Sign-in failed. Check your email and password and try again."


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def normalise_email(email: str) -> str:
    return email.strip().lower()


def roles_of(db: Session, user_id: uuid.UUID) -> list[Role]:
    rows = db.scalars(select(RoleAssignment.role).where(RoleAssignment.user_id == user_id))
    found = {Role(value) for value in rows}
    return [role for role in Role if role in found]


@dataclass(frozen=True)
class Account:
    user: User
    credential: UserCredential | None
    roles: list[Role]


def get_account(db: Session, user_id: uuid.UUID) -> Account:
    user = db.get(User, user_id)
    if user is None:
        raise AppError("not_found", "Account not found.", 404)
    return Account(user, db.get(UserCredential, user_id), roles_of(db, user_id))


def authenticate(db: Session, settings: Settings, email: str, password: str) -> Account:
    """Check an email and password. Repeated failures lock the account for a while."""
    user = db.scalar(select(User).where(func.lower(User.email) == normalise_email(email)))
    credential = db.get(UserCredential, user.id) if user else None
    if user is None or credential is None:
        passwords.burn_time(password)
        raise AppError("invalid_credentials", _SIGN_IN_FAILED, 401)

    now = _now()
    locked_until = _aware(credential.locked_until)
    if locked_until and locked_until > now:
        passwords.burn_time(password)
        minutes = max(1, round((locked_until - now).total_seconds() / 60))
        raise AppError(
            "account_locked",
            f"Too many failed attempts. Try again in {minutes} minute(s).",
            429,
        )

    if not passwords.verify_password(password, credential.password_hash):
        credential.failed_attempts += 1
        if credential.failed_attempts >= settings.auth_max_failed_attempts:
            credential.locked_until = now + timedelta(minutes=settings.auth_lockout_minutes)
            credential.failed_attempts = 0
            append_event(
                db,
                entity_type=ENTITY_ACCOUNT,
                entity_id=user.id,
                action="account.locked",
                actor_id=None,
                details={"minutes": settings.auth_lockout_minutes},
            )
        db.commit()
        raise AppError("invalid_credentials", _SIGN_IN_FAILED, 401)

    if not user.is_active:
        raise AppError("account_disabled", "This account has been disabled.", 403)

    credential.failed_attempts = 0
    credential.locked_until = None
    credential.last_sign_in_at = now
    db.commit()
    return Account(user, credential, roles_of(db, user.id))


def live_roles(db: Session, user_id: uuid.UUID, version: object) -> tuple[list[Role], bool]:
    """Current roles for a built-in token and whether a password change is pending.

    Fails if the account was disabled or its password changed since the token was issued.
    While a temporary password is in use the account holds no roles, so it can only
    change its password."""
    user = db.get(User, user_id)
    credential = db.get(UserCredential, user_id)
    if user is None or credential is None or not user.is_active:
        raise AppError("unauthorized", "Authentication required.", 401)
    if not isinstance(version, int) or version != credential.token_version:
        raise AppError("session_expired", "Your session has ended. Sign in again.", 401)
    if credential.must_change_password:
        return [], True
    return roles_of(db, user_id), False


def _set_roles(
    db: Session, user_id: uuid.UUID, roles: list[Role], actor: uuid.UUID | None
) -> tuple[list[Role], list[Role]]:
    current = set(roles_of(db, user_id))
    wanted = set(roles)
    for role in wanted - current:
        db.add(RoleAssignment(user_id=user_id, role=role, granted_by=actor))
    for row in db.scalars(select(RoleAssignment).where(RoleAssignment.user_id == user_id)):
        if Role(row.role) not in wanted:
            db.delete(row)
    return sorted(wanted - current), sorted(current - wanted)


def create_account(
    db: Session,
    *,
    email: str,
    display_name: str | None,
    roles: list[Role],
    password: str | None,
    actor: uuid.UUID | None,
) -> tuple[Account, str | None]:
    """Create an account. Without a password, a temporary one is generated and returned
    once; the user must change it at first sign-in."""
    email = normalise_email(email)
    if db.scalar(select(User.id).where(func.lower(User.email) == email)) is not None:
        raise AppError("email_taken", "An account with this email already exists.", 409)
    if not roles:
        raise AppError("roles_required", "Give the account at least one role.", 422)

    temporary = None
    if password is None:
        temporary = passwords.generate_temporary_password()
        password = temporary
    elif problem := passwords.password_problem(password, email):
        raise AppError("weak_password", problem, 422)

    user = User(id=uuid.uuid4(), email=email, display_name=display_name, is_active=True)
    db.add(user)
    db.flush()
    db.add(
        UserCredential(
            user_id=user.id,
            password_hash=passwords.hash_password(password),
            must_change_password=temporary is not None,
        )
    )
    _set_roles(db, user.id, roles, actor)
    db.flush()
    append_event(
        db,
        entity_type=ENTITY_ACCOUNT,
        entity_id=user.id,
        action="account.created",
        actor_id=actor,
        details={"roles": sorted(r.value for r in roles), "temporary_password": bool(temporary)},
    )
    db.commit()
    return get_account(db, user.id), temporary


def update_account(
    db: Session,
    user_id: uuid.UUID,
    *,
    actor: uuid.UUID,
    roles: list[Role] | None,
    is_active: bool | None,
    display_name: str | None,
) -> Account:
    account = get_account(db, user_id)
    if user_id == actor and (
        is_active is False or (roles is not None and Role.SYSTEM_ADMIN not in roles)
    ):
        raise AppError(
            "cannot_demote_self",
            "You cannot disable your own account or remove your own system admin role.",
            409,
        )
    details: dict[str, object] = {}
    if roles is not None:
        if not roles:
            raise AppError("roles_required", "Give the account at least one role.", 422)
        added, removed = _set_roles(db, user_id, roles, actor)
        if added or removed:
            details["roles_added"] = [r.value for r in added]
            details["roles_removed"] = [r.value for r in removed]
    if is_active is not None and is_active != account.user.is_active:
        account.user.is_active = is_active
        details["is_active"] = is_active
    if display_name is not None and display_name != account.user.display_name:
        account.user.display_name = display_name or None
        details["display_name_changed"] = True
    if not details:
        raise AppError("no_change", "Nothing was changed.", 409)
    account.user.updated_at = _now()
    db.flush()
    _assert_an_admin_remains(db)
    append_event(
        db,
        entity_type=ENTITY_ACCOUNT,
        entity_id=user_id,
        action="account.updated",
        actor_id=actor,
        details=details,
    )
    db.commit()
    return get_account(db, user_id)


def _assert_an_admin_remains(db: Session) -> None:
    active_admins = db.scalar(
        select(func.count())
        .select_from(RoleAssignment)
        .join(User, User.id == RoleAssignment.user_id)
        .where(RoleAssignment.role == Role.SYSTEM_ADMIN, User.is_active.is_(True))
    )
    if not active_admins:
        db.rollback()
        raise AppError("last_admin", "At least one active system admin must remain.", 409)


def reset_password(db: Session, user_id: uuid.UUID, actor: uuid.UUID) -> str:
    """Give the account a new temporary password and end its current sessions."""
    account = get_account(db, user_id)
    temporary = passwords.generate_temporary_password()
    if account.credential is None:
        db.add(
            UserCredential(
                user_id=user_id,
                password_hash=passwords.hash_password(temporary),
                must_change_password=True,
            )
        )
    else:
        account.credential.password_hash = passwords.hash_password(temporary)
        account.credential.token_version += 1
        account.credential.must_change_password = True
        account.credential.failed_attempts = 0
        account.credential.locked_until = None
        account.credential.password_changed_at = _now()
    db.flush()
    append_event(
        db,
        entity_type=ENTITY_ACCOUNT,
        entity_id=user_id,
        action="account.password_reset",
        actor_id=actor,
    )
    db.commit()
    return temporary


def change_password(db: Session, user_id: uuid.UUID, current: str, new: str) -> Account:
    account = get_account(db, user_id)
    credential = account.credential
    if credential is None or not passwords.verify_password(current, credential.password_hash):
        raise AppError("invalid_credentials", "Your current password is not correct.", 401)
    if current == new:
        raise AppError("weak_password", "Choose a password you have not used here.", 422)
    if problem := passwords.password_problem(new, account.user.email):
        raise AppError("weak_password", problem, 422)
    credential.password_hash = passwords.hash_password(new)
    credential.token_version += 1
    credential.must_change_password = False
    credential.password_changed_at = _now()
    db.flush()
    append_event(
        db,
        entity_type=ENTITY_ACCOUNT,
        entity_id=user_id,
        action="account.password_changed",
        actor_id=user_id,
    )
    db.commit()
    return get_account(db, user_id)


def list_accounts(db: Session) -> list[Account]:
    users = list(db.scalars(select(User).order_by(User.email)))
    roles: dict[uuid.UUID, set[Role]] = {}
    for user_id, role in db.execute(select(RoleAssignment.user_id, RoleAssignment.role)):
        roles.setdefault(user_id, set()).add(Role(role))
    credentials = {
        c.user_id: c
        for c in db.scalars(
            select(UserCredential).where(UserCredential.user_id.in_([u.id for u in users]))
        )
    }
    return [
        Account(u, credentials.get(u.id), [r for r in Role if r in roles.get(u.id, set())])
        for u in users
    ]
