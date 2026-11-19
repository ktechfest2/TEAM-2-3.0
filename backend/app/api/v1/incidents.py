"""Incident routes.

Anyone may submit a report and check its progress with the reference. Reading reports
needs an incident staff role; changing a review status needs a reviewer role. Public
routes return only counts and reviewer-written summaries of verified incidents."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import SlidingWindowLimiter, client_key
from app.core.security import Principal, get_optional_principal, require_roles
from app.db.enums import (
    INCIDENT_REVIEWER_ROLES,
    INCIDENT_STAFF_ROLES,
    IncidentCategory,
    IncidentSeverity,
    IncidentStatus,
    UpdateCategory,
    UpdateVerificationStatus,
)
from app.db.models import IncidentReport
from app.directory.repository import DirectoryRepository, UpdateQuery, get_directory
from app.evidence.db import get_evidence_db
from app.evidence.storage import EvidenceStorage, get_storage
from app.incidents import service, workflow
from app.incidents.service import AttachmentUpload, IncidentFilters, IncidentInput
from app.schemas.analytics import DEMO_LABEL
from app.schemas.common import PageResponse
from app.schemas.incidents import (
    AreaCount,
    AttachmentView,
    CountItem,
    IncidentDetail,
    IncidentPage,
    IncidentReceipt,
    IncidentReviewIn,
    IncidentStats,
    IncidentSummary,
    IncidentTrack,
    LocationName,
    PublicIncident,
    PublicIncidentSummary,
    ReviewView,
    TimelinePoint,
)
from app.schemas.updates import ElectionUpdate

router = APIRouter(prefix="/incidents", tags=["incidents"])
public_router = APIRouter(prefix="/public", tags=["public"])

Db = Annotated[Session, Depends(get_evidence_db)]
Directory = Annotated[DirectoryRepository, Depends(get_directory)]
Storage = Annotated[EvidenceStorage, Depends(get_storage)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Staff = Annotated[Principal, Depends(require_roles(*INCIDENT_STAFF_ROLES))]
Reviewer = Annotated[Principal, Depends(require_roles(*INCIDENT_REVIEWER_ROLES))]
MaybePrincipal = Annotated[Principal | None, Depends(get_optional_principal)]
PageNumber = Annotated[int, Query(ge=1, le=10_000)]
PageSize = Annotated[int, Query(ge=1, le=100)]

_MULTIPART_OVERHEAD = 64 * 1024
CATEGORY_LABEL = {
    IncidentCategory.VIOLENCE: "Electoral violence or threats",
    IncidentCategory.INTIMIDATION: "Voter intimidation",
    IncidentCategory.VOTE_BUYING: "Vote-buying allegation",
    IncidentCategory.DELAYED_OFFICIALS: "Delayed election officials",
    IncidentCategory.POLLING_UNIT_RELOCATION: "Polling-unit relocation",
    IncidentCategory.VOTING_DISRUPTION: "Voting disruption",
    IncidentCategory.ACCESSIBILITY: "Accessibility problem",
    IncidentCategory.MISINFORMATION: "Misinformation",
    IncidentCategory.OTHER: "Other electoral concern",
}
STATUS_LABEL = {s: s.value.replace("_", " ").capitalize() for s in IncidentStatus}

def _now() -> datetime:
    return datetime.now(UTC)

def _submission_limiter(request: Request, settings: AppSettings) -> SlidingWindowLimiter:
    state = request.app.state
    limiter = getattr(state, "incident_limiter", None)
    if limiter is None or limiter.limit != settings.incident_submissions_per_hour:
        limiter = SlidingWindowLimiter(settings.incident_submissions_per_hour, 3600)
        state.incident_limiter = limiter
    return limiter

def _location(reg, level: str, area_id: uuid.UUID | None) -> LocationName | None:
    if area_id is None:
        return None
    source = {"state": reg.states, "lga": reg.lgas, "ward": reg.wards, "unit": reg.units}[
        level
    ].get(area_id)
    if source is None:
        return LocationName(id=area_id, name="Unknown")
    return LocationName(id=source.id, name=source.name, code=source.code)

def _reporter(incident: IncidentReport) -> str:
    if incident.reporter_user_id is None:
        return "anonymous"
    return "protected" if incident.identity_protected else "account"

def _summary_fields(incident: IncidentReport, directory: DirectoryRepository) -> dict:
    reg = service.names(directory)
    duplicate_ref = None
    if incident.possible_duplicate_of_id:
        for item in (incident.triage or {}).get("similar_reports", []):
            if item.get("id") == str(incident.possible_duplicate_of_id):
                duplicate_ref = item.get("reference")
        duplicate_ref = duplicate_ref or str(incident.possible_duplicate_of_id)
    triage = incident.triage or {}
    excerpt = (
        incident.description
        if len(incident.description) <= 140
        else (incident.description[:137].rstrip() + "...")
    )
    return {
        "id": incident.id,
        "reference": incident.reference,
        "election_id": incident.election_id,
        "category": incident.category,
        "reported_category": incident.reported_category,
        "severity": incident.severity,
        "status": incident.status,
        "band": service.band_of(incident),
        "state": _location(reg, "state", incident.state_id),
        "lga": _location(reg, "lga", incident.lga_id),
        "ward": _location(reg, "ward", incident.ward_id),
        "polling_unit": _location(reg, "unit", incident.polling_unit_id),
        "occurred_at": incident.occurred_at,
        "time_is_approximate": incident.time_is_approximate,
        "received_at": incident.received_at,
        "status_changed_at": incident.status_changed_at,
        "excerpt": excerpt,
        "has_attachment": not any(
            m.get("field") == "image" for m in triage.get("missing_information", [])
        ),
        "possible_duplicate_of": duplicate_ref,
        "similar_count": len(triage.get("similar_reports", [])),
        "missing_count": len(triage.get("missing_information", [])),
        "reporter": _reporter(incident),
        "is_public": incident.is_public,
    }

def _detail(
    db: Session, incident: IncidentReport, directory: DirectoryRepository, principal: Principal
) -> IncidentDetail:
    can_review = any(r in INCIDENT_REVIEWER_ROLES for r in principal.roles) and not (
        service.is_own_report(incident, principal)
    )
    return IncidentDetail(
        **_summary_fields(incident, directory),
        description=incident.description,
        latitude=incident.latitude,
        longitude=incident.longitude,
        triage=incident.triage or {},
        attachments=[
            AttachmentView(
                id=a.id,
                content_type=a.content_type,
                byte_size=a.byte_size,
                width=a.width,
                height=a.height,
                sha256=a.sha256,
                created_at=a.created_at,
            )
            for a in service.attachments(db, incident.id)
        ],
        reviews=[
            ReviewView(
                id=r.id,
                reviewer_id=r.reviewer_id,
                previous_status=r.previous_status,
                new_status=r.new_status,
                reason=r.reason,
                evidence_refs=r.evidence_refs,
                category_from=r.category_from,
                category_to=r.category_to,
                severity_from=r.severity_from,
                severity_to=r.severity_to,
                public_summary=r.public_summary,
                published=r.published,
                created_at=r.created_at,
            )
            for r in service.reviews(db, incident.id)
        ],
        public_summary=incident.public_summary,
        published_at=incident.published_at,
        resolution_basis=incident.resolution_basis,
        # Protected reporters are never identified, not even to staff.
        reporter_user_id=(incident.reporter_user_id if _reporter(incident) == "account" else None),
        allowed_transitions=service.allowed_transitions(incident) if can_review else [],
        can_review=can_review,
        channel=incident.channel,
    )

def _filters(
    election_id: uuid.UUID | None,
    state_id: uuid.UUID | None,
    lga_id: uuid.UUID | None,
    ward_id: uuid.UUID | None,
    category: IncidentCategory | None,
    severity: IncidentSeverity | None,
    status_filter: IncidentStatus | None,
    occurred_from: datetime | None,
    occurred_to: datetime | None,
    queue: bool = False,
) -> IncidentFilters:
    if occurred_from and occurred_to and occurred_from > occurred_to:
        raise AppError("validation_error", "occurred_from must be on or before occurred_to.", 422)
    return IncidentFilters(
        election_id=election_id,
        state_id=state_id,
        lga_id=lga_id,
        ward_id=ward_id,
        category=category,
        severity=severity,
        status=status_filter,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        queue=queue,
    )

class FilterParams:
    def __init__(
        self,
        election_id: uuid.UUID | None = None,
        state_id: uuid.UUID | None = None,
        lga_id: uuid.UUID | None = None,
        ward_id: uuid.UUID | None = None,
        category: IncidentCategory | None = None,
        severity: IncidentSeverity | None = None,
        status: IncidentStatus | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
    ) -> None:
        self.args = (
            election_id,
            state_id,
            lga_id,
            ward_id,
            category,
            severity,
            status,
            occurred_from,
            occurred_to,
        )

Filters = Annotated[FilterParams, Depends()]

@router.post("", response_model=IncidentReceipt, status_code=status.HTTP_201_CREATED)
async def submit_incident(
    request: Request,
    response: Response,
    db: Db,
    directory: Directory,
    storage: Storage,
    settings: AppSettings,
    principal: MaybePrincipal,
    election_id: Annotated[uuid.UUID, Form()],
    category: Annotated[IncidentCategory, Form()],
    description: Annotated[str, Form(min_length=20, max_length=2000)],
    state_id: Annotated[uuid.UUID, Form()],
    lga_id: Annotated[uuid.UUID, Form()],
    occurred_at: Annotated[datetime, Form()],
    ward_id: Annotated[uuid.UUID | None, Form()] = None,
    polling_unit_id: Annotated[uuid.UUID | None, Form()] = None,
    time_is_approximate: Annotated[bool, Form()] = True,
    latitude: Annotated[float | None, Form(ge=-90, le=90)] = None,
    longitude: Annotated[float | None, Form(ge=-180, le=180)] = None,
    protect_identity: Annotated[bool, Form()] = False,
    file: Annotated[UploadFile | None, File(description="Optional JPEG, PNG or WebP photo")] = None,
    idempotency_key: Annotated[uuid.UUID | None, Header(alias="Idempotency-Key")] = None,
) -> IncidentReceipt:
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit():
        if int(content_length) > settings.incident_attachment_max_bytes + _MULTIPART_OVERHEAD:
            raise AppError("file_too_large", "The photo is too large.", 413)
    # A retry of an already-received report (same Idempotency-Key) is not counted again.
    is_retry = idempotency_key is not None and db.scalar(
        select(IncidentReport.id).where(IncidentReport.client_generated_id == idempotency_key)
    )
    if not is_retry:
        allowed, retry_after = _submission_limiter(request, settings).check(
            client_key(request, settings.trust_proxy_headers)
        )
        if not allowed:
            raise AppError(
                "rate_limited",
                "Too many reports from this connection. Please wait and try again.",
                429,
                details={"retry_after_seconds": retry_after},
            )

    upload = None
    if file is not None and file.filename:
        data = await file.read(settings.incident_attachment_max_bytes + 1)
        upload = AttachmentUpload(data=data, filename=file.filename, content_type=file.content_type)

    result = service.submit(
        db,
        directory,
        storage,
        settings,
        IncidentInput(
            election_id=election_id,
            category=category,
            description=description,
            state_id=state_id,
            lga_id=lga_id,
            ward_id=ward_id,
            polling_unit_id=polling_unit_id,
            occurred_at=occurred_at,
            time_is_approximate=time_is_approximate,
            latitude=latitude,
            longitude=longitude,
            protect_identity=protect_identity,
            client_id=idempotency_key,
        ),
        upload,
        principal,
    )
    incident = result.incident
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return IncidentReceipt(
        id=incident.id,
        reference=incident.reference,
        status=incident.status,
        band=service.band_of(incident),
        received_at=incident.received_at,
        created=result.created,
        duplicate=False,
        personal_data_redacted=bool((incident.triage or {}).get("personal_data_redacted")),
        attachment_stored=result.attachment_stored
        or (not result.created and bool(service.attachments(db, incident.id))),
    )

@router.get("/track/{reference}", response_model=IncidentTrack)
def track_incident(db: Db, reference: str) -> IncidentTrack:
    """Progress of one report, for the person holding its reference. No report content."""
    if len(reference) > 24:
        raise AppError("not_found", "No report has that reference.", 404)
    incident = service.find_by_reference(db, reference)
    if incident is None:
        raise AppError("not_found", "No report has that reference.", 404)
    band = service.band_of(incident)
    return IncidentTrack(
        reference=incident.reference,
        band=band,
        band_label=workflow.BAND_LABEL[band],
        received_at=incident.received_at,
        last_updated_at=incident.status_changed_at,
        public_summary=incident.public_summary if incident.is_public else None,
    )

@router.get("/stats", response_model=IncidentStats)
def incident_stats(db: Db, directory: Directory, _staff: Staff, filters: Filters) -> IncidentStats:
    data = service.statistics(db, directory, _filters(*filters.args))
    return IncidentStats(
        total=data["total"],
        awaiting_review=data["awaiting_review"],
        under_investigation=data["under_investigation"],
        verified=data["verified"],
        unverified=data["unverified"],
        inconclusive=data["inconclusive"],
        rejected=data["rejected"],
        resolved=data["resolved"],
        possible_duplicates=data["possible_duplicates"],
        critical_open=data["critical_open"],
        by_category=[
            CountItem(key=c.value, label=CATEGORY_LABEL[c], count=data["by_category"][c])
            for c in IncidentCategory
        ],
        by_status=[
            CountItem(key=s.value, label=STATUS_LABEL[s], count=data["by_status"][s])
            for s in IncidentStatus
        ],
        by_severity=[
            CountItem(key=s.value, label=s.value.capitalize(), count=data["by_severity"][s])
            for s in IncidentSeverity
        ],
        by_band=[
            CountItem(key=b, label=label, count=data["by_band"][b])
            for b, label in workflow.BAND_LABEL.items()
        ],
        by_state=[AreaCount(**item) for item in data["by_state"]],
        by_lga=[AreaCount(**item) for item in data["by_lga"]],
        timeline_bucket=data["timeline_bucket"],
        timeline=[TimelinePoint(period=p, count=n) for p, n in data["timeline"]],
        generated_at=_now(),
    )

@router.get("", response_model=IncidentPage)
def list_incidents(
    db: Db,
    directory: Directory,
    _staff: Staff,
    filters: Filters,
    queue: bool = False,
    page: PageNumber = 1,
    page_size: PageSize = 25,
) -> IncidentPage:
    rows, total = service.search(db, _filters(*filters.args, queue=queue), page, page_size)
    return IncidentPage(
        items=[IncidentSummary(**_summary_fields(r, directory)) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=service.total_pages(total, page_size),
        generated_at=_now(),
    )

@router.get("/{incident_id}", response_model=IncidentDetail)
def get_incident(
    db: Db, directory: Directory, principal: Staff, incident_id: uuid.UUID
) -> IncidentDetail:
    return _detail(db, service.get_incident(db, incident_id), directory, principal)

@router.get("/{incident_id}/attachments/{attachment_id}")
def get_attachment(
    db: Db, storage: Storage, _staff: Staff, incident_id: uuid.UUID, attachment_id: uuid.UUID
) -> Response:
    attachment, data = service.read_attachment(db, storage, incident_id, attachment_id)
    return Response(
        content=data,
        media_type=attachment.content_type,
        headers={
            "X-Content-SHA256": attachment.sha256,
            "Content-Disposition": "inline",
            "Content-Security-Policy": "default-src 'none'",
        },
    )

@router.post("/{incident_id}/review", response_model=IncidentDetail)
def review_incident(
    db: Db,
    directory: Directory,
    principal: Reviewer,
    incident_id: uuid.UUID,
    payload: IncidentReviewIn,
) -> IncidentDetail:
    incident = service.get_incident(db, incident_id)
    service.review(db, incident, principal, payload)
    db.refresh(incident)
    return _detail(db, incident, directory, principal)

@public_router.get("/election-updates", response_model=PageResponse[ElectionUpdate])
def public_election_updates(
    directory: Directory,
    category: UpdateCategory | None = None,
    verification_status: UpdateVerificationStatus | None = None,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> PageResponse[ElectionUpdate]:
    """The announcements service, as used by the web app, USSD and SMS."""
    result = directory.list_updates(
        UpdateQuery(category=category, verification_status=verification_status), page, page_size
    )
    return PageResponse[ElectionUpdate](
        items=result.items,
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        total_pages=result.total_pages,
        data_source=directory.source,
        generated_at=_now(),
    )

@public_router.get("/incidents", response_model=PublicIncidentSummary)
def public_incidents(
    db: Db, directory: Directory, election_id: Annotated[uuid.UUID, Query()]
) -> PublicIncidentSummary:
    election = directory.get_election(election_id)
    if election is None:
        raise AppError("not_found", "Election not found.", 404)
    counts, published = service.public_items(db, election_id)
    reg = service.names(directory)
    return PublicIncidentSummary(
        election_id=election_id,
        by_band=[
            CountItem(key=b, label=label, count=counts[b])
            for b, label in workflow.BAND_LABEL.items()
        ],
        published=[
            PublicIncident(
                category=r.category,
                state=reg.states[r.state_id].name if r.state_id in reg.states else "Unknown",
                lga=reg.lgas[r.lga_id].name if r.lga_id in reg.lgas else "Unknown",
                occurred_on=service.utc(r.occurred_at).date(),
                summary=r.public_summary or "",
                published_at=r.published_at or r.received_at,
            )
            for r in published
        ],
        demo_label=DEMO_LABEL if election.is_demo or directory.source.kind == "demo" else None,
        generated_at=_now(),
    )
