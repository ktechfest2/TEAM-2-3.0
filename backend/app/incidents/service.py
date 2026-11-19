"""Incident submission, review and monitoring queries.

Reports are stored as written (after masking phone numbers and e-mail addresses).
Triage output and reviewer decisions sit beside the report and never replace it."""

import io
import math
import secrets
import uuid
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.registry import Registry, register
from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import Principal
from app.db.enums import IncidentCategory, IncidentSeverity, IncidentStatus
from app.db.models import IncidentAttachment, IncidentReport, IncidentReview
from app.directory.repository import DirectoryRepository
from app.evidence.audit import append_event
from app.evidence.db import ensure_user
from app.evidence.hashing import sha256_bytes
from app.evidence.image_validation import validate_image
from app.evidence.storage import EvidenceStorage, read_verified
from app.incidents import triage, workflow
from app.incidents.workflow import TRANSITIONS
from app.schemas.incidents import IncidentReviewIn

I = IncidentStatus  # noqa: E741
ENTITY_INCIDENT = "incident_report"
_REFERENCE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32: no I, L, O, U
_CLOCK_SKEW = timedelta(minutes=10)
_MAX_AGE = timedelta(days=90)
_DUPLICATE_WINDOW = timedelta(hours=24)
SIMILAR_THRESHOLD = 0.5
SAME_UNIT_THRESHOLD = 0.25
DUPLICATE_THRESHOLD = 0.7

class IncidentAction:
    RECEIVED = "incident.received"
    ATTACHMENT_STORED = "incident.attachment_stored"
    REVIEWED = "incident.reviewed"
    PUBLISHED = "incident.published"
    UNPUBLISHED = "incident.unpublished"

@dataclass(frozen=True)
class IncidentInput:
    election_id: uuid.UUID
    category: IncidentCategory
    description: str
    state_id: uuid.UUID
    lga_id: uuid.UUID
    ward_id: uuid.UUID | None
    polling_unit_id: uuid.UUID | None
    occurred_at: datetime
    time_is_approximate: bool
    latitude: float | None
    longitude: float | None
    protect_identity: bool
    client_id: uuid.UUID | None
    channel: str = "web"

@dataclass(frozen=True)
class AttachmentUpload:
    data: bytes
    filename: str | None
    content_type: str | None

@dataclass(frozen=True)
class Submission:
    incident: IncidentReport
    created: bool
    redacted: bool
    attachment_stored: bool

@dataclass(frozen=True)
class IncidentFilters:
    election_id: uuid.UUID | None = None
    state_id: uuid.UUID | None = None
    lga_id: uuid.UUID | None = None
    ward_id: uuid.UUID | None = None
    category: IncidentCategory | None = None
    severity: IncidentSeverity | None = None
    status: IncidentStatus | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    queue: bool = False

def utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes; they were written as UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

def _now() -> datetime:
    return datetime.now(UTC)

def _invalid(code: str, message: str, status: int = 422) -> AppError:
    return AppError(code, message, status_code=status)

def new_reference() -> str:
    chars = "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(12))
    return f"VV-{chars[:4]}-{chars[4:8]}-{chars[8:]}"

def normalise_reference(value: str) -> str:
    cleaned = value.strip().upper().replace(" ", "")
    return cleaned.replace("O", "0").replace("I", "1").replace("L", "1")

def names(directory: DirectoryRepository) -> Registry:
    return register(directory)

def _check_location(directory: DirectoryRepository, data: IncidentInput) -> IncidentInput:
    reg = names(directory)
    state = reg.states.get(data.state_id)
    if state is None:
        raise _invalid("unknown_state", "The state is not recognised.")
    lga = reg.lgas.get(data.lga_id)
    if lga is None or lga.state_id != state.id:
        raise _invalid("unknown_lga", "The LGA is not in the selected state.")
    ward_id = data.ward_id
    if ward_id is not None:
        ward = reg.wards.get(ward_id)
        if ward is None or ward.lga_id != lga.id:
            raise _invalid("unknown_ward", "The ward is not in the selected LGA.")
    if data.polling_unit_id is not None:
        unit = reg.units.get(data.polling_unit_id)
        if unit is None or unit.lga_id != lga.id:
            raise _invalid("unknown_polling_unit", "The polling unit is not in the selected LGA.")
        if ward_id is not None and unit.ward_id != ward_id:
            raise _invalid("unknown_polling_unit", "The polling unit is not in the selected ward.")
        ward_id = unit.ward_id
    if (data.latitude is None) != (data.longitude is None):
        raise _invalid("invalid_coordinates", "Give both latitude and longitude, or neither.")
    return replace(data, ward_id=ward_id)

def _strip_metadata(data: bytes) -> tuple[bytes, int, int]:
    """Re-encode as JPEG without EXIF, GPS or camera details. Orientation is applied
    first so the picture still displays the right way up."""
    with Image.open(io.BytesIO(data)) as source:
        upright = ImageOps.exif_transpose(source).convert("RGB")
        buffer = io.BytesIO()
        upright.save(buffer, "JPEG", quality=85, optimize=True)
        return buffer.getvalue(), upright.width, upright.height

def _store_attachment(
    db: Session,
    storage: EvidenceStorage,
    settings: Settings,
    incident: IncidentReport,
    upload: AttachmentUpload,
) -> None:
    limits = settings.model_copy(
        update={
            "evidence_max_bytes": settings.incident_attachment_max_bytes,
            "evidence_min_dimension": settings.incident_attachment_min_dimension,
        }
    )
    validate_image(
        upload.data,
        filename=upload.filename,
        declared_content_type=upload.content_type,
        settings=limits,
    )
    clean, width, height = _strip_metadata(upload.data)
    digest = sha256_bytes(clean)
    key = f"incidents/{incident.id}/{uuid.uuid4().hex}.jpg"
    storage.put(key, clean, "image/jpeg")
    attachment = IncidentAttachment(
        incident_id=incident.id,
        storage_bucket=storage.bucket,
        storage_path=key,
        content_type="image/jpeg",
        byte_size=len(clean),
        width=width,
        height=height,
        sha256=digest,
    )
    db.add(attachment)
    db.flush()
    append_event(
        db,
        entity_type=ENTITY_INCIDENT,
        entity_id=incident.id,
        action=IncidentAction.ATTACHMENT_STORED,
        actor_id=None,
        details={"attachment_id": str(attachment.id), "sha256": digest, "metadata_removed": True},
    )

def attachments(db: Session, incident_id: uuid.UUID) -> list[IncidentAttachment]:
    return list(
        db.scalars(
            select(IncidentAttachment)
            .where(IncidentAttachment.incident_id == incident_id)
            .order_by(IncidentAttachment.created_at)
        )
    )

def read_attachment(
    db: Session, storage: EvidenceStorage, incident_id: uuid.UUID, attachment_id: uuid.UUID
) -> tuple[IncidentAttachment, bytes]:
    attachment = db.get(IncidentAttachment, attachment_id)
    if attachment is None or attachment.incident_id != incident_id:
        raise AppError("not_found", "Attachment not found.", 404)
    return attachment, read_verified(storage, attachment.storage_path, attachment.sha256)

def _similar_reports(
    db: Session, settings: Settings, data: IncidentInput, words: frozenset[str]
) -> tuple[list[dict[str, Any]], list[IncidentReport]]:
    window = timedelta(hours=settings.incident_similarity_window_hours)
    occurred = utc(data.occurred_at)
    candidates = db.scalars(
        select(IncidentReport)
        .where(
            IncidentReport.election_id == data.election_id,
            IncidentReport.lga_id == data.lga_id,
            IncidentReport.category == data.category,
            IncidentReport.status != I.REJECTED,
            IncidentReport.occurred_at >= occurred - window,
            IncidentReport.occurred_at <= occurred + window,
        )
        .order_by(IncidentReport.received_at)
        .limit(200)
    ).all()
    found: list[tuple[float, IncidentReport, bool]] = []
    for other in candidates:
        same_unit = (
            data.polling_unit_id is not None and other.polling_unit_id == data.polling_unit_id
        )
        score = triage.similarity(words, triage.tokens(other.description))
        if score >= SIMILAR_THRESHOLD or (same_unit and score >= SAME_UNIT_THRESHOLD):
            found.append((score, other, same_unit))
    found.sort(key=lambda item: item[0], reverse=True)
    summary = [
        {
            "id": str(other.id),
            "reference": other.reference,
            "similarity": round(score, 2),
            "same_polling_unit": same_unit,
        }
        for score, other, same_unit in found[:5]
    ]
    return summary, [other for _, other, _ in found]

def _link_back(new: IncidentReport, others: list[IncidentReport], words: frozenset[str]) -> None:
    """Record the new report on the earlier similar reports, so each sees its corroboration."""
    for other in others[:20]:
        data = dict(other.triage or {})
        similar = list(data.get("similar_reports", []))
        if any(item.get("id") == str(new.id) for item in similar):
            continue
        score = triage.similarity(words, triage.tokens(other.description))
        similar.append(
            {
                "id": str(new.id),
                "reference": new.reference,
                "similarity": round(score, 2),
                "same_polling_unit": bool(
                    new.polling_unit_id and new.polling_unit_id == other.polling_unit_id
                ),
            }
        )
        similar.sort(key=lambda item: item["similarity"], reverse=True)
        data["similar_reports"] = similar[:5]
        data["corroborating_reports"] = int(data.get("corroborating_reports", 0)) + 1
        other.triage = data

def submit(
    db: Session,
    directory: DirectoryRepository,
    storage: EvidenceStorage,
    settings: Settings,
    raw: IncidentInput,
    upload: AttachmentUpload | None,
    principal: Principal | None,
) -> Submission:
    if raw.client_id is not None:
        existing = db.scalar(
            select(IncidentReport).where(IncidentReport.client_generated_id == raw.client_id)
        )
        if existing is not None:
            return Submission(existing, created=False, redacted=False, attachment_stored=False)

    if directory.get_election(raw.election_id) is None:
        raise _invalid("unknown_election", "The election is not recognised.")
    data = _check_location(directory, raw)
    now = _now()
    occurred = utc(data.occurred_at)
    if occurred > now + _CLOCK_SKEW:
        raise _invalid("invalid_time", "The incident time cannot be in the future.")
    if occurred < now - _MAX_AGE:
        raise _invalid("invalid_time", "Incidents older than 90 days cannot be reported here.")

    description, redacted = triage.clean_text(data.description)
    if len(description) < 20:
        raise _invalid("description_too_short", "Describe what happened in at least 20 characters.")

    fingerprint = triage.fingerprint(
        election_id=data.election_id,
        category=data.category,
        lga_id=data.lga_id,
        ward_id=data.ward_id,
        polling_unit_id=data.polling_unit_id,
        description=description,
    )
    duplicate = db.scalar(
        select(IncidentReport.id).where(
            IncidentReport.content_fingerprint == fingerprint,
            IncidentReport.received_at >= now - _DUPLICATE_WINDOW,
        )
    )
    if duplicate is not None:
        raise AppError(
            "duplicate_report",
            "An identical report for this place was received in the last 24 hours. It is "
            "already in the review queue.",
            409,
        )

    words = triage.tokens(description)
    similar, similar_rows = _similar_reports(db, settings, data, words)
    if principal is not None:
        similar_rows = [r for r in similar_rows if r.reporter_user_id != principal.user_id]
        similar = [s for s in similar if any(str(r.id) == s["id"] for r in similar_rows)]
    result = triage.TriageResult(
        classification=triage.classify(description),
        severity=triage.assess_severity(data.category, description),
        missing=triage.missing_information(
            description=description,
            ward_id=data.ward_id,
            polling_unit_id=data.polling_unit_id,
            time_is_approximate=data.time_is_approximate,
            has_coordinates=data.latitude is not None,
            has_attachment=upload is not None,
        ),
        redacted=redacted,
        similar=similar,
    )
    duplicate_of = next(
        (
            row
            for row in sorted(similar_rows, key=lambda r: utc(r.received_at))
            if triage.similarity(words, triage.tokens(row.description)) >= DUPLICATE_THRESHOLD
        ),
        None,
    )

    if principal is not None:
        ensure_user(db, principal)
    reference = new_reference()
    while db.scalar(select(IncidentReport.id).where(IncidentReport.reference == reference)):
        reference = new_reference()
    incident = IncidentReport(
        id=uuid.uuid4(),
        reference=reference,
        election_id=data.election_id,
        reported_category=data.category,
        category=data.category,
        description=description,
        state_id=data.state_id,
        lga_id=data.lga_id,
        ward_id=data.ward_id,
        polling_unit_id=data.polling_unit_id,
        occurred_at=occurred,
        time_is_approximate=data.time_is_approximate,
        latitude=data.latitude,
        longitude=data.longitude,
        status=I.RECEIVED,
        status_changed_at=now,
        severity=result.severity.severity,
        triage=result.as_json(data.category),
        possible_duplicate_of_id=duplicate_of.id if duplicate_of else None,
        content_fingerprint=fingerprint,
        area_key=triage.area_key(data.election_id, data.lga_id, data.ward_id),
        reporter_user_id=principal.user_id if principal else None,
        identity_protected=bool(principal and data.protect_identity),
        client_generated_id=data.client_id,
        channel=data.channel,
        received_at=now,
    )
    db.add(incident)
    db.flush()
    _link_back(incident, similar_rows, words)
    if principal is None:
        reporter = "anonymous"
    else:
        reporter = "protected" if incident.identity_protected else "account"
    append_event(
        db,
        entity_type=ENTITY_INCIDENT,
        entity_id=incident.id,
        action=IncidentAction.RECEIVED,
        # Anonymous and protected reports are logged as system events, so the audit
        # trail does not reveal who reported them.
        actor_id=principal.user_id if reporter == "account" and principal else None,
        details={
            "reference": reference,
            "category": data.category.value,
            "severity": result.severity.severity.value,
            "channel": data.channel,
            "reporter": reporter,
            "has_attachment": upload is not None,
            "possible_duplicate_of": str(duplicate_of.id) if duplicate_of else None,
            "similar_reports": len(similar),
            "personal_data_redacted": redacted,
        },
    )
    stored = False
    if upload is not None:
        _store_attachment(db, storage, settings, incident, upload)
        stored = True
    db.commit()
    return Submission(incident, created=True, redacted=redacted, attachment_stored=stored)

def get_incident(db: Session, incident_id: uuid.UUID) -> IncidentReport:
    incident = db.get(IncidentReport, incident_id)
    if incident is None:
        raise AppError("not_found", "Incident report not found.", 404)
    return incident

def reviews(db: Session, incident_id: uuid.UUID) -> list[IncidentReview]:
    return list(
        db.scalars(
            select(IncidentReview)
            .where(IncidentReview.incident_id == incident_id)
            .order_by(IncidentReview.created_at)
        )
    )

def allowed_transitions(incident: IncidentReport) -> list[IncidentStatus]:
    return list(TRANSITIONS[I(incident.status)])

def is_own_report(incident: IncidentReport, principal: Principal) -> bool:
    return incident.reporter_user_id is not None and incident.reporter_user_id == principal.user_id

def review(
    db: Session, incident: IncidentReport, principal: Principal, payload: IncidentReviewIn
) -> IncidentReview:
    if is_own_report(incident, principal):
        raise AppError("forbidden", "You cannot review a report you submitted.", 403)
    current = I(incident.status)
    target = payload.new_status
    category_to = payload.category if payload.category not in (None, incident.category) else None
    severity_to = payload.severity if payload.severity not in (None, incident.severity) else None
    publish_change = payload.publish is not None and payload.publish != incident.is_public
    summary_change = (
        payload.public_summary is not None and payload.public_summary != incident.public_summary
    )

    if target != current and target not in TRANSITIONS[current]:
        allowed = ", ".join(s.value for s in TRANSITIONS[current]) or "none"
        raise AppError(
            "invalid_transition",
            f"A {current.value} report cannot move to {target.value}. Allowed: {allowed}.",
            409,
        )
    if target == current and not (category_to or severity_to or publish_change or summary_change):
        raise AppError("no_change", "The review does not change anything.", 409)
    if target in workflow.NEEDS_EVIDENCE and target != current and not payload.evidence_refs:
        raise _invalid(
            "evidence_required",
            "Verifying an incident needs at least one reference to supporting evidence.",
        )

    basis = incident.resolution_basis
    if target == I.RESOLVED and current != I.RESOLVED:
        basis = current
    elif target != I.RESOLVED:
        basis = None

    summary = incident.public_summary
    if payload.public_summary is not None:
        summary, _ = triage.clean_text(payload.public_summary)
    publish = incident.is_public if payload.publish is None else payload.publish
    if publish and not workflow.can_publish(target, basis):
        if payload.publish:
            raise _invalid(
                "not_publishable", "Only verified incidents can be published to the public."
            )
        publish = False
    if publish and not summary:
        raise _invalid("summary_required", "Write a public summary before publishing.")

    ensure_user(db, principal)
    now = _now()
    record = IncidentReview(
        incident_id=incident.id,
        reviewer_id=principal.user_id,
        previous_status=current,
        new_status=target,
        reason=triage.clean_text(payload.reason)[0],
        evidence_refs=payload.evidence_refs,
        category_from=incident.category if category_to else None,
        category_to=category_to,
        severity_from=incident.severity if severity_to else None,
        severity_to=severity_to,
        public_summary=summary if summary_change else None,
        published=publish,
    )
    db.add(record)
    was_public = incident.is_public
    if target != current:
        incident.status = target
        incident.status_changed_at = now
    incident.resolution_basis = basis
    if category_to:
        incident.category = category_to
    if severity_to:
        incident.severity = severity_to
    incident.public_summary = summary
    incident.is_public = publish
    if publish and not was_public:
        incident.published_at = now
    db.flush()
    append_event(
        db,
        entity_type=ENTITY_INCIDENT,
        entity_id=incident.id,
        action=IncidentAction.REVIEWED,
        actor_id=principal.user_id,
        details={
            "review_id": str(record.id),
            "previous_status": current.value,
            "new_status": target.value,
            "category_to": category_to.value if category_to else None,
            "severity_to": severity_to.value if severity_to else None,
            "evidence_refs": len(payload.evidence_refs),
            "reason_sha256": sha256_bytes(record.reason.encode()),
        },
    )
    if publish != was_public:
        append_event(
            db,
            entity_type=ENTITY_INCIDENT,
            entity_id=incident.id,
            action=IncidentAction.PUBLISHED if publish else IncidentAction.UNPUBLISHED,
            actor_id=principal.user_id,
            details={"review_id": str(record.id)},
        )
    db.commit()
    return record

def corroborating(incident: IncidentReport) -> int:
    return int((incident.triage or {}).get("corroborating_reports", 0))

def band_of(incident: IncidentReport) -> workflow.Band:
    basis = I(incident.resolution_basis) if incident.resolution_basis else None
    return workflow.band(I(incident.status), corroborating(incident), basis)

def _where(filters: IncidentFilters) -> list:
    clauses: list = []
    if filters.election_id:
        clauses.append(IncidentReport.election_id == filters.election_id)
    if filters.state_id:
        clauses.append(IncidentReport.state_id == filters.state_id)
    if filters.lga_id:
        clauses.append(IncidentReport.lga_id == filters.lga_id)
    if filters.ward_id:
        clauses.append(IncidentReport.ward_id == filters.ward_id)
    if filters.category:
        clauses.append(IncidentReport.category == filters.category)
    if filters.severity:
        clauses.append(IncidentReport.severity == filters.severity)
    if filters.status:
        clauses.append(IncidentReport.status == filters.status)
    if filters.occurred_from:
        clauses.append(IncidentReport.occurred_at >= utc(filters.occurred_from))
    if filters.occurred_to:
        clauses.append(IncidentReport.occurred_at <= utc(filters.occurred_to))
    if filters.queue:
        clauses.append(IncidentReport.status.in_(workflow.OPEN))
    return clauses

_SEVERITY_RANK = {
    IncidentSeverity.CRITICAL: 0,
    IncidentSeverity.HIGH: 1,
    IncidentSeverity.MEDIUM: 2,
    IncidentSeverity.LOW: 3,
}

def search(
    db: Session, filters: IncidentFilters, page: int, page_size: int
) -> tuple[list[IncidentReport], int]:
    rows = list(db.scalars(select(IncidentReport).where(*_where(filters))))
    if filters.queue:
        # Review queue: most severe first, then oldest first.
        rows.sort(key=lambda r: (_SEVERITY_RANK[IncidentSeverity(r.severity)], utc(r.received_at)))
    else:
        rows.sort(key=lambda r: utc(r.received_at), reverse=True)
    start = (page - 1) * page_size
    return rows[start : start + page_size], len(rows)

def total_pages(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / page_size))

def statistics(db: Session, directory: DirectoryRepository, filters: IncidentFilters) -> dict:
    rows = list(db.scalars(select(IncidentReport).where(*_where(filters))))
    reg = names(directory)
    status_counts = Counter(I(r.status) for r in rows)
    verified = status_counts[I.VERIFIED] + sum(
        1 for r in rows if r.status == I.RESOLVED and r.resolution_basis == I.VERIFIED
    )
    by_state = Counter(r.state_id for r in rows)
    by_lga = Counter(r.lga_id for r in rows)
    times = sorted(utc(r.occurred_at) for r in rows)
    hourly = bool(times) and times[-1] - times[0] <= timedelta(hours=48)
    fmt = "%Y-%m-%dT%H:00Z" if hourly else "%Y-%m-%d"
    timeline = Counter(t.strftime(fmt) for t in times)

    def state_name(state_id: uuid.UUID) -> str:
        state = reg.states.get(state_id)
        return state.name if state else "Unknown state"

    return {
        "total": len(rows),
        "awaiting_review": sum(status_counts[s] for s in workflow.AWAITING_REVIEW),
        "under_investigation": sum(status_counts[s] for s in workflow.UNDER_INVESTIGATION),
        "verified": verified,
        "unverified": status_counts[I.UNVERIFIED],
        "inconclusive": status_counts[I.INCONCLUSIVE],
        "rejected": status_counts[I.REJECTED],
        "resolved": status_counts[I.RESOLVED],
        "possible_duplicates": sum(1 for r in rows if r.possible_duplicate_of_id),
        "critical_open": sum(
            1 for r in rows if r.severity == IncidentSeverity.CRITICAL and r.status in workflow.OPEN
        ),
        "by_category": Counter(IncidentCategory(r.category) for r in rows),
        "by_status": status_counts,
        "by_severity": Counter(IncidentSeverity(r.severity) for r in rows),
        "by_band": Counter(band_of(r) for r in rows),
        "by_state": [
            {"id": sid, "name": state_name(sid), "count": n} for sid, n in by_state.most_common()
        ],
        "by_lga": [
            {
                "id": lid,
                "name": reg.lgas[lid].name if lid in reg.lgas else "Unknown LGA",
                "parent": state_name(reg.lgas[lid].state_id) if lid in reg.lgas else None,
                "count": n,
            }
            for lid, n in by_lga.most_common(20)
        ],
        "timeline_bucket": "hour" if hourly else "day",
        "timeline": sorted(timeline.items()),
    }

def public_items(db: Session, election_id: uuid.UUID) -> tuple[Counter, list[IncidentReport]]:
    rows = list(db.scalars(select(IncidentReport).where(IncidentReport.election_id == election_id)))
    published = [r for r in rows if r.is_public and r.public_summary]
    published.sort(key=lambda r: utc(r.published_at or r.received_at), reverse=True)
    return Counter(band_of(r) for r in rows), published[:50]

def find_by_reference(db: Session, reference: str) -> IncidentReport | None:
    return db.scalar(
        select(IncidentReport).where(IncidentReport.reference == normalise_reference(reference))
    )
