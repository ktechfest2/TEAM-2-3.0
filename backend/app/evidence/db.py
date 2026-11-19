"""Database sessions for the evidence workflow.

With DATABASE_URL set (required in production) the shared Postgres engine is used and
the schema comes from Alembic migrations. Without it, development and test runs use a
local SQLite file holding only the evidence tables. SQLite does not enforce the foreign
keys to elections and polling units; the API validates those identifiers itself."""

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.analytics.hooks  # noqa: F401  (registers aggregation refresh on commit)
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import Principal
from app.db import models
from app.db.session import get_session_factory

DEV_TABLES = [
    models.User.__table__,
    models.RoleAssignment.__table__,
    models.UserCredential.__table__,
    models.Election.__table__,
    models.State.__table__,
    models.Lga.__table__,
    models.Ward.__table__,
    models.PollingUnit.__table__,
    models.PollingUnitNotice.__table__,
    models.RelocationReport.__table__,
    models.ElectionUpdate.__table__,
    models.EvidenceSubmission.__table__,
    models.EvidenceImage.__table__,
    models.OcrExtraction.__table__,
    models.ExtractedResultField.__table__,
    models.ResultValidation.__table__,
    models.SubmissionComparison.__table__,
    models.AnomalyAlert.__table__,
    models.EvidenceReview.__table__,
    models.AuditEvent.__table__,
    models.PollingUnitResult.__table__,
    models.PollingUnitResultMetric.__table__,
    models.IncidentReport.__table__,
    models.IncidentAttachment.__table__,
    models.IncidentReview.__table__,
    models.SmsMessage.__table__,
]


def create_dev_engine(path: str) -> Engine:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(connection, _record) -> None:  # type: ignore[no-untyped-def]
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    models.Base.metadata.create_all(engine, tables=DEV_TABLES)
    return engine


@lru_cache
def _dev_session_factory(path: str) -> sessionmaker[Session]:
    return sessionmaker(bind=create_dev_engine(path), autoflush=False, expire_on_commit=False)


def evidence_session_factory() -> sessionmaker[Session]:
    settings = get_settings()
    if settings.database_url:
        return get_session_factory()
    if settings.is_production:
        raise AppError("database_unavailable", "The database is not configured.", 503)
    return _dev_session_factory(settings.dev_database_path)


def get_evidence_db() -> Iterator[Session]:
    session = evidence_session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ensure_user(db: Session, principal: Principal) -> None:
    """Mirror the authenticated user into `users` so foreign keys resolve. Caller commits."""
    if db.get(models.User, principal.user_id) is not None:
        return
    placeholder = f"{principal.user_id}@users.invalid"
    email = principal.email or placeholder
    # The address may belong to another profile row (for example after an email change).
    if db.scalar(select(models.User.id).where(models.User.email == email)) is not None:
        email = placeholder
    db.add(models.User(id=principal.user_id, email=email, is_active=True))
    db.flush()
