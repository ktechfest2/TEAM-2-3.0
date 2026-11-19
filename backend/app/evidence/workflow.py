"""Controlled workflow transitions.

VERIFIED is reachable only from REVIEWED, and only through the review service once
enough distinct reviewers have approved the same result fingerprint. OCR success,
passing arithmetic, matching submissions or a quiet anomaly engine never verify a
record on their own. VoteTrace statuses are not INEC declarations."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.enums import EvidenceStatus as S
from app.db.models import EvidenceSubmission
from app.evidence.audit import AuditAction, append_event

TRANSITIONS: dict[S, frozenset[S]] = {
    S.RECEIVED: frozenset({S.PROCESSING}),
    # PROCESSING → RECEIVED when processing fails and can be retried.
    S.PROCESSING: frozenset({S.EXTRACTED, S.RECEIVED}),
    S.EXTRACTED: frozenset({S.PROCESSING, S.ARITHMETIC_VALIDATED, S.FLAGGED_FOR_REVIEW}),
    S.ARITHMETIC_VALIDATED: frozenset({S.CROSS_CHECKED, S.FLAGGED_FOR_REVIEW, S.EXTRACTED}),
    S.CROSS_CHECKED: frozenset(
        {S.FLAGGED_FOR_REVIEW, S.UNDER_HUMAN_REVIEW, S.EXTRACTED, S.ARITHMETIC_VALIDATED}
    ),
    S.FLAGGED_FOR_REVIEW: frozenset(
        {S.UNDER_HUMAN_REVIEW, S.EXTRACTED, S.ARITHMETIC_VALIDATED, S.PROCESSING}
    ),
    S.UNDER_HUMAN_REVIEW: frozenset({S.REVIEWED, S.REJECTED, S.EXTRACTED}),
    S.REVIEWED: frozenset({S.VERIFIED, S.UNDER_HUMAN_REVIEW, S.EXTRACTED}),
    S.VERIFIED: frozenset(),
    S.REJECTED: frozenset(),
}

# Statuses in which values may still be corrected or reprocessed.
EDITABLE = frozenset(
    {
        S.EXTRACTED,
        S.ARITHMETIC_VALIDATED,
        S.CROSS_CHECKED,
        S.FLAGGED_FOR_REVIEW,
        S.UNDER_HUMAN_REVIEW,
    }
)
PROCESSABLE = frozenset({S.RECEIVED, S.EXTRACTED, S.FLAGGED_FOR_REVIEW})
VALIDATABLE = frozenset(
    {S.EXTRACTED, S.ARITHMETIC_VALIDATED, S.CROSS_CHECKED, S.FLAGGED_FOR_REVIEW}
)
REVIEWABLE = frozenset({S.CROSS_CHECKED, S.FLAGGED_FOR_REVIEW})
TERMINAL = frozenset({S.VERIFIED, S.REJECTED})


def can_transition(current: S, target: S) -> bool:
    return target in TRANSITIONS[current]


def transition(
    db: Session,
    submission: EvidenceSubmission,
    target: S,
    *,
    actor_id: uuid.UUID | None,
    reason: str,
) -> None:
    current = S(submission.workflow_status)
    if current == target:
        return
    if not can_transition(current, target):
        raise AppError(
            "invalid_transition",
            f"A submission cannot move from {current.value} to {target.value}.",
            status_code=409,
        )
    submission.workflow_status = target
    submission.status_changed_at = datetime.now(UTC)
    append_event(
        db,
        entity_id=submission.id,
        action=AuditAction.STATUS_CHANGED,
        actor_id=actor_id,
        details={"from": current.value, "to": target.value, "reason": reason},
    )


def walk(
    db: Session,
    submission: EvidenceSubmission,
    path: list[S],
    *,
    actor_id: uuid.UUID | None,
    reason: str,
) -> None:
    for target in path:
        transition(db, submission, target, actor_id=actor_id, reason=reason)
