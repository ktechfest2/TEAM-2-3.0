"""Recompute the aggregation row of one polling unit from its source records."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.analytics.policy import PolicyOutcome, SubmissionState, decide
from app.analytics.registry import registry_for
from app.core.errors import AppError
from app.db.enums import EvidenceStatus, ResultStream
from app.db.enums import PollingUnitResultStatus as R
from app.db.models import (
    AnomalyAlert,
    EvidenceImage,
    EvidenceSubmission,
    PollingUnitResult,
    PollingUnitResultMetric,
)
from app.directory.repository import DirectoryRepository, get_directory
from app.evidence.audit import append_event
from app.evidence.service import latest_validation

logger = logging.getLogger(__name__)

ENTITY_PU_RESULT = "polling_unit_result"
ACTION_RECALCULATED = "aggregation.recalculated"

_COMPARED = (
    "status",
    "submission_count",
    "accepted_count",
    "independent_count",
    "rejected_count",
    "distinct_results",
    "has_flagged",
    "has_anomaly",
    "reported_result_hash",
    "verified_result_hash",
    "source_submission_ids",
    "contributing_submission_ids",
    "first_reported_at",
    "verified_at",
    "last_submission_at",
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def submission_state(db: Session, submission: EvidenceSubmission) -> SubmissionState:
    validation = latest_validation(db, submission.id)
    perceptual = db.scalar(
        select(EvidenceImage.perceptual_hash).where(
            EvidenceImage.submission_id == submission.id, EvidenceImage.kind == "original"
        )
    )
    has_alerts = False
    values: dict[str, Any] = {}
    if validation is not None:
        values = {key: value for key, value in validation.result_snapshot["fields"]}
        run_id = validation.report.get("analysis_run_id")
        if run_id:
            has_alerts = (
                db.scalar(
                    select(AnomalyAlert.id)
                    .where(
                        AnomalyAlert.submission_id == submission.id,
                        AnomalyAlert.analysis_run_id == uuid.UUID(run_id),
                    )
                    .limit(1)
                )
                is not None
            )
    return SubmissionState(
        id=submission.id,
        submitted_by=submission.submitted_by,
        status=EvidenceStatus(submission.workflow_status),
        received_at=_utc(submission.received_at),  # type: ignore[arg-type]
        status_changed_at=_utc(submission.status_changed_at),  # type: ignore[arg-type]
        original_sha256=submission.original_sha256,
        perceptual_hash=perceptual,
        validation_passed=None if validation is None else validation.passed,
        validated_at=None if validation is None else _utc(validation.created_at),
        result_hash=None if validation is None else validation.result_hash,
        values=values,
        has_alerts=has_alerts,
    )


def _locked_row(
    db: Session, election_id: uuid.UUID, polling_unit_id: uuid.UUID, placeholder: dict[str, Any]
) -> tuple[PollingUnitResult, bool]:
    """Fetch the unit's row with a row lock, creating it first if needed. Concurrent
    transactions for the same unit serialise here; the unique constraint guarantees one
    row per election and polling unit."""
    query = (
        select(PollingUnitResult)
        .where(
            PollingUnitResult.election_id == election_id,
            PollingUnitResult.polling_unit_id == polling_unit_id,
        )
        .with_for_update()
    )
    row = db.scalar(query)
    if row is not None:
        return row, False
    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    db.execute(
        insert(PollingUnitResult)
        .values(**placeholder)
        .on_conflict_do_nothing(index_elements=["election_id", "polling_unit_id"])
    )
    row = db.scalar(query.execution_options(populate_existing=True))
    assert row is not None
    return row, row.id == placeholder["id"]


def _metric_rows(row: PollingUnitResult, outcome: PolicyOutcome) -> list[PollingUnitResultMetric]:
    rows = []
    for stream, metrics in (
        (ResultStream.REPORTED, outcome.reported_metrics),
        (ResultStream.VERIFIED, outcome.verified_metrics),
    ):
        for metric, value in sorted(metrics.items()):
            rows.append(
                PollingUnitResultMetric(
                    result_id=row.id,
                    election_id=row.election_id,
                    polling_unit_id=row.polling_unit_id,
                    ward_id=row.ward_id,
                    lga_id=row.lga_id,
                    state_id=row.state_id,
                    stream=stream,
                    metric=metric,
                    value=value,
                )
            )
    return rows


def refresh_polling_unit(
    db: Session,
    election_id: uuid.UUID,
    polling_unit_id: uuid.UUID,
    directory: DirectoryRepository | None = None,
) -> dict[str, Any] | None:
    """Recompute one unit. Returns a change notification, or None if nothing changed or
    the unit is not in the register for this election."""
    try:
        directory = directory or get_directory()
    except AppError:
        logger.warning("analytics_skipped_directory_unavailable")
        return None
    election = directory.get_election(election_id)
    if election is None:
        return None
    unit = registry_for(directory, election).units.get(polling_unit_id)
    if unit is None:
        logger.warning("analytics_skipped_unknown_polling_unit")
        return None

    submissions = db.scalars(
        select(EvidenceSubmission).where(
            EvidenceSubmission.election_id == election_id,
            EvidenceSubmission.polling_unit_id == polling_unit_id,
        )
    ).all()
    outcome = decide([submission_state(db, s) for s in submissions])
    now = datetime.now(UTC)

    row, created = _locked_row(
        db,
        election_id,
        polling_unit_id,
        {
            "id": uuid.uuid4(),
            "election_id": election_id,
            "polling_unit_id": polling_unit_id,
            "ward_id": unit.ward_id,
            "lga_id": unit.lga_id,
            "state_id": unit.state_id,
            "status": R.NOT_REPORTING,
            "source_submission_ids": [],
            "contributing_submission_ids": [],
            "submission_count": 0,
            "accepted_count": 0,
            "independent_count": 0,
            "rejected_count": 0,
            "distinct_results": 0,
            "has_flagged": False,
            "has_anomaly": False,
            "is_demo": election.is_demo,
            "revision": 1,
            "updated_at": now,
        },
    )
    previous_status = None if created else R(row.status)
    current = {name: getattr(outcome, name) for name in _COMPARED}
    stored = {
        name: _utc(getattr(row, name)) if isinstance(getattr(row, name), datetime) else None
        for name in ("first_reported_at", "verified_at", "last_submission_at")
    }
    unchanged = not created and all(
        (stored[name] if name in stored else getattr(row, name)) == value
        for name, value in current.items()
    )
    if unchanged:
        return None

    for name, value in current.items():
        setattr(row, name, value)
    row.is_demo = election.is_demo
    row.revision = 1 if created else row.revision + 1
    row.updated_at = now
    db.execute(delete(PollingUnitResultMetric).where(PollingUnitResultMetric.result_id == row.id))
    db.add_all(_metric_rows(row, outcome))
    db.flush()

    append_event(
        db,
        entity_id=row.id,
        entity_type=ENTITY_PU_RESULT,
        action=ACTION_RECALCULATED,
        actor_id=None,
        details={
            "election_id": election_id,
            "polling_unit_id": polling_unit_id,
            "revision": row.revision,
            "previous_status": None if previous_status is None else previous_status.value,
            "status": outcome.status.value,
            "reported_result_hash": outcome.reported_result_hash,
            "verified_result_hash": outcome.verified_result_hash,
            "source_submission_ids": outcome.source_submission_ids,
            "contributing_submission_ids": outcome.contributing_submission_ids,
            "distinct_results": outcome.distinct_results,
        },
    )
    return {
        "type": "polling_unit_result",
        "election_id": str(election_id),
        "polling_unit_id": str(polling_unit_id),
        "ward_id": str(unit.ward_id),
        "lga_id": str(unit.lga_id),
        "state_id": str(unit.state_id),
        "status": outcome.status.value,
        "previous_status": None if previous_status is None else previous_status.value,
        "revision": row.revision,
        "changed_at": now.isoformat(),
    }


def rebuild_election(
    db: Session, election_id: uuid.UUID, directory: DirectoryRepository | None = None
) -> list[dict[str, Any]]:
    """Recompute every unit that has submissions or an existing row. Caller commits."""
    with_submissions = set(
        db.scalars(
            select(EvidenceSubmission.polling_unit_id)
            .where(EvidenceSubmission.election_id == election_id)
            .distinct()
        )
    )
    with_rows = set(
        db.scalars(
            select(PollingUnitResult.polling_unit_id).where(
                PollingUnitResult.election_id == election_id
            )
        )
    )
    changes = []
    for polling_unit_id in sorted(with_submissions | with_rows, key=str):
        change = refresh_polling_unit(db, election_id, polling_unit_id, directory)
        if change is not None:
            changes.append(change)
    return changes
