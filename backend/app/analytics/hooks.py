"""Keep polling-unit aggregations in step with evidence, inside the same transaction.

Every evidence workflow step (receipt, processing, correction, validation, review)
changes its EvidenceSubmission row. Those rows are noted at flush time; just before the
commit, only the affected polling units are recomputed, so the derived rows commit or
roll back together with the change that caused them. Change notifications are sent only
after the commit succeeds."""

import logging
from itertools import chain

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.models import EvidenceSubmission

logger = logging.getLogger(__name__)

_PENDING = "verivote.analytics.pending"
_EVENTS = "verivote.analytics.events"
_REFRESHING = "verivote.analytics.refreshing"


def mark_changed(session: Session, election_id, polling_unit_id) -> None:  # type: ignore[no-untyped-def]
    session.info.setdefault(_PENDING, set()).add((election_id, polling_unit_id))


@event.listens_for(Session, "before_flush")
def _track(session: Session, _context, _instances) -> None:  # type: ignore[no-untyped-def]
    for obj in chain(session.new, session.dirty):
        if isinstance(obj, EvidenceSubmission) and (
            obj in session.new or session.is_modified(obj, include_collections=False)
        ):
            mark_changed(session, obj.election_id, obj.polling_unit_id)


@event.listens_for(Session, "before_commit")
def _refresh(session: Session) -> None:
    if session.info.get(_REFRESHING) or not session.info.get(_PENDING):
        return
    from app.analytics.refresh import refresh_polling_unit

    session.flush()
    pending = sorted(session.info.pop(_PENDING, set()), key=lambda key: (str(key[0]), str(key[1])))
    session.info[_REFRESHING] = True
    try:
        for election_id, polling_unit_id in pending:
            change = refresh_polling_unit(session, election_id, polling_unit_id)
            if change is not None:
                session.info.setdefault(_EVENTS, []).append(change)
        session.flush()
    finally:
        session.info.pop(_REFRESHING, None)


@event.listens_for(Session, "after_commit")
def _publish(session: Session) -> None:
    changes = session.info.pop(_EVENTS, None)
    if not changes:
        return
    from app.analytics.events import broker

    for change in changes:
        broker.publish(change)


@event.listens_for(Session, "after_rollback")
def _discard(session: Session) -> None:
    session.info.pop(_PENDING, None)
    session.info.pop(_EVENTS, None)
