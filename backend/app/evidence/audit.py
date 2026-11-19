"""Append-only, hash-chained audit events.

Each entity (for example one evidence submission) has its own chain. An event's
hash covers its content and the previous event's hash, so altering or removing an
earlier event breaks every later link. This makes tampering *evident*; it does not
prevent a privileged database administrator from rewriting the whole chain. Keep
periodic external copies of chain heads if stronger guarantees are needed."""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import request_id_ctx
from app.db.models import AuditEvent
from app.evidence.hashing import GENESIS_HASH, canonical_json, canonical_timestamp, sha256_bytes

AUDIT_SCHEMA = "verivote.audit.v1"
ENTITY_SUBMISSION = "evidence_submission"


class AuditAction:
    EVIDENCE_RECEIVED = "evidence.received"
    EVIDENCE_HASHED = "evidence.hashed"
    INTEGRITY_VERIFIED = "evidence.integrity_verified"
    INTEGRITY_FAILED = "evidence.integrity_failed"
    OCR_STARTED = "ocr.started"
    OCR_COMPLETED = "ocr.completed"
    OCR_FAILED = "ocr.failed"
    FIELD_CORRECTED = "extraction.corrected"
    VALIDATION_COMPLETED = "validation.completed"
    COMPARISON_COMPLETED = "comparison.completed"
    ANOMALY_DETECTED = "anomaly.detected"
    REVIEW_RECORDED = "review.recorded"
    STATUS_CHANGED = "status.changed"


def _as_utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes; they were written as UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def compute_event_hash(
    *,
    event_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    sequence: int,
    action: str,
    actor_id: uuid.UUID | None,
    actor_type: str,
    created_at: datetime,
    details: dict[str, Any],
    previous_hash: str,
) -> str:
    payload = {
        "schema": AUDIT_SCHEMA,
        "id": str(event_id),
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "sequence": sequence,
        "action": action,
        "actor_id": None if actor_id is None else str(actor_id),
        "actor_type": actor_type,
        "created_at": canonical_timestamp(_as_utc(created_at)),
        "details": details,
        "previous_hash": previous_hash,
    }
    return sha256_bytes(canonical_json(payload))


def _hash_of(event: AuditEvent) -> str:
    return compute_event_hash(
        event_id=event.id,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        sequence=event.sequence,
        action=event.action,
        actor_id=event.actor_id,
        actor_type=event.actor_type,
        created_at=event.created_at,
        details=event.details,
        previous_hash=event.previous_hash,
    )


def append_event(
    db: Session,
    *,
    entity_id: uuid.UUID,
    action: str,
    actor_id: uuid.UUID | None,
    details: dict[str, Any] | None = None,
    entity_type: str = ENTITY_SUBMISSION,
) -> AuditEvent:
    """Add the next event to the entity's chain. Caller commits.

    Concurrent writers to the same chain collide on the unique (entity, sequence)
    constraint, so one of them fails instead of forking the chain."""
    last = db.scalar(
        select(AuditEvent)
        .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
        .order_by(AuditEvent.sequence.desc())
        .limit(1)
    )
    sequence = 1 if last is None else last.sequence + 1
    previous_hash = GENESIS_HASH if last is None else last.event_hash
    # Round-trip through canonical JSON so the stored details hash identically on read.
    clean_details: dict[str, Any] = {} if details is None else _normalise(details)
    created_at = datetime.now(UTC)
    event_id = uuid.uuid4()
    actor_type = "user" if actor_id else "system"
    event = AuditEvent(
        id=event_id,
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        sequence=sequence,
        previous_hash=previous_hash,
        event_hash=compute_event_hash(
            event_id=event_id,
            entity_type=entity_type,
            entity_id=entity_id,
            sequence=sequence,
            action=action,
            actor_id=actor_id,
            actor_type=actor_type,
            created_at=created_at,
            details=clean_details,
            previous_hash=previous_hash,
        ),
        request_id=request_id_ctx.get(),
        details=clean_details,
        created_at=created_at,
    )
    db.add(event)
    db.flush()
    return event


def _normalise(details: dict[str, Any]) -> dict[str, Any]:
    return json.loads(canonical_json(details))


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    length: int
    head_hash: str | None
    broken_at_sequence: int | None
    problem: str | None


def verify_chain(events: list[AuditEvent]) -> ChainVerification:
    expected_previous = GENESIS_HASH
    for position, event in enumerate(sorted(events, key=lambda e: e.sequence), start=1):
        if event.sequence != position:
            return ChainVerification(False, len(events), None, event.sequence, "missing_event")
        if event.previous_hash != expected_previous:
            return ChainVerification(False, len(events), None, event.sequence, "broken_link")
        if _hash_of(event) != event.event_hash:
            return ChainVerification(False, len(events), None, event.sequence, "content_altered")
        expected_previous = event.event_hash
    head = expected_previous if events else None
    return ChainVerification(True, len(events), head, None, None)


def load_chain(
    db: Session, entity_id: uuid.UUID, entity_type: str = ENTITY_SUBMISSION
) -> list[AuditEvent]:
    return list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
            .order_by(AuditEvent.sequence)
        )
    )
