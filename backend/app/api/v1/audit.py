"""Read-only access to the hash-chained audit trail for auditors and administrators."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import Principal, require_roles
from app.db.enums import Role
from app.db.models import AuditEvent, User
from app.evidence.audit import load_chain, verify_chain
from app.evidence.db import get_evidence_db
from app.schemas.evidence import UtcDateTime

router = APIRouter(prefix="/admin/audit-events", tags=["audit"])

Db = Annotated[Session, Depends(get_evidence_db)]
AuditReader = Annotated[
    Principal, Depends(require_roles(Role.AUDITOR, Role.ELECTION_ADMIN, Role.SYSTEM_ADMIN))
]


class AuditEventOut(BaseModel):
    id: uuid.UUID
    created_at: UtcDateTime
    action: str
    entity_type: str
    entity_id: uuid.UUID
    sequence: int
    actor_type: str
    actor_id: uuid.UUID | None
    actor_email: str | None
    request_id: str | None
    details: dict[str, Any]
    event_hash: str


class AuditPage(BaseModel):
    items: list[AuditEventOut]
    total: int
    page: int
    page_size: int
    entity_types: list[str]


class ChainOut(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    valid: bool
    events: int
    head_hash: str | None
    broken_at_sequence: int | None
    problem: str | None


@router.get("", response_model=AuditPage)
def list_audit_events(
    _: AuditReader,
    db: Db,
    entity_type: Annotated[str | None, Query(max_length=100)] = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AuditPage:
    conditions = []
    if entity_type:
        conditions.append(AuditEvent.entity_type == entity_type)
    if action:
        conditions.append(AuditEvent.action.startswith(action, autoescape=True))
    if entity_id:
        conditions.append(AuditEvent.entity_id == entity_id)
    if actor_id:
        conditions.append(AuditEvent.actor_id == actor_id)
    if since:
        conditions.append(AuditEvent.created_at >= since)
    if until:
        conditions.append(AuditEvent.created_at <= until)

    total = db.scalar(select(func.count()).select_from(AuditEvent).where(*conditions)) or 0
    rows = db.execute(
        select(AuditEvent, User.email)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .where(*conditions)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.sequence.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    entity_types = sorted(db.scalars(select(AuditEvent.entity_type).distinct()))
    return AuditPage(
        items=[
            AuditEventOut(
                id=event.id,
                created_at=event.created_at,
                action=event.action,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                sequence=event.sequence,
                actor_type=event.actor_type,
                actor_id=event.actor_id,
                actor_email=email,
                request_id=event.request_id,
                details=event.details or {},
                event_hash=event.event_hash,
            )
            for event, email in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        entity_types=entity_types,
    )


@router.get("/chains/{entity_type}/{entity_id}", response_model=ChainOut)
def verify_audit_chain(entity_type: str, entity_id: uuid.UUID, _: AuditReader, db: Db) -> ChainOut:
    """Recompute every hash in one record's chain and report the first break, if any."""
    entity_type = entity_type[:100]
    result = verify_chain(load_chain(db, entity_id, entity_type))
    return ChainOut(
        entity_type=entity_type,
        entity_id=entity_id,
        valid=result.valid,
        events=result.length,
        head_hash=result.head_hash,
        broken_at_sequence=result.broken_at_sequence,
        problem=result.problem,
    )
