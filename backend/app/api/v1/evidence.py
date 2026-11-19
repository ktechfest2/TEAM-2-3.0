"""Evidence routes. Every route requires authentication. Field submitters see only their
own submissions; staff see all. Statuses change only through server-side actions."""

import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import Principal, require_roles
from app.db.enums import (
    EVIDENCE_REVIEWER_ROLES,
    EVIDENCE_STAFF_ROLES,
    EVIDENCE_SUBMITTER_ROLES,
    EvidenceImageKind,
    EvidenceStatus,
)
from app.db.models import AnomalyAlert, EvidenceImage, EvidenceSubmission
from app.directory.repository import DirectoryRepository, get_directory
from app.evidence import service, workflow
from app.evidence.audit import load_chain, verify_chain
from app.evidence.db import get_evidence_db
from app.evidence.field_mapping import field_labels
from app.evidence.ocr import OcrProvider, get_ocr_provider
from app.evidence.service import Correction, Upload
from app.evidence.storage import EvidenceStorage, IntegrityError, get_storage, read_verified
from app.evidence.templates import get_template
from app.schemas.elections import Election
from app.schemas.evidence import (
    AlertView,
    AnomalyReport,
    AuditEventView,
    AuditTrail,
    ComparisonView,
    ElectionRef,
    EvidenceDetail,
    EvidenceImageView,
    EvidencePage,
    EvidenceSummary,
    ExtractedField,
    ExtractionCorrectionIn,
    ExtractionView,
    FieldVersion,
    IntegrityReport,
    PollingUnitRef,
    ReviewHistory,
    ReviewIn,
    ReviewOutcome,
    ReviewView,
    SubmissionReceipt,
    ValidationView,
)
from app.schemas.polling_units import PollingUnitDetail

router = APIRouter(prefix="/evidence", tags=["evidence"])

S = EvidenceStatus
ALL_EVIDENCE_ROLES = tuple(dict.fromkeys(EVIDENCE_SUBMITTER_ROLES + EVIDENCE_STAFF_ROLES))

AnyEvidenceUser = Annotated[Principal, Depends(require_roles(*ALL_EVIDENCE_ROLES))]
Submitter = Annotated[Principal, Depends(require_roles(*EVIDENCE_SUBMITTER_ROLES))]
Staff = Annotated[Principal, Depends(require_roles(*EVIDENCE_STAFF_ROLES))]
Reviewer = Annotated[Principal, Depends(require_roles(*EVIDENCE_REVIEWER_ROLES))]
Db = Annotated[Session, Depends(get_evidence_db)]
Directory = Annotated[DirectoryRepository, Depends(get_directory)]
Storage = Annotated[EvidenceStorage, Depends(get_storage)]
Ocr = Annotated[OcrProvider, Depends(get_ocr_provider)]
AppSettings = Annotated[Settings, Depends(get_settings)]

# Uploads are expensive. This sits on top of the global per-client API limit.
_upload_limiter = SlidingWindowLimiter(limit=20, window_seconds=60)
_MULTIPART_OVERHEAD = 64 * 1024
_CLOCK_SKEW = timedelta(minutes=10)
REVIEW_QUEUE = (S.CROSS_CHECKED, S.FLAGGED_FOR_REVIEW, S.UNDER_HUMAN_REVIEW, S.REVIEWED)

def _is_staff(principal: Principal) -> bool:
    return any(role in EVIDENCE_STAFF_ROLES for role in principal.roles)

def _is_reviewer(principal: Principal) -> bool:
    return any(role in EVIDENCE_REVIEWER_ROLES for role in principal.roles)

def _load(db: Session, submission_id: uuid.UUID, principal: Principal) -> EvidenceSubmission:
    submission = service.get_submission(db, submission_id)
    if not _is_staff(principal) and submission.submitted_by != principal.user_id:
        # Same response as a missing record: do not reveal other users' submissions.
        raise AppError("not_found", "Evidence submission not found.", 404)
    return submission

def _require_editor(submission: EvidenceSubmission, principal: Principal) -> None:
    """Owners may work on their own submission until review starts; reviewers may act on any."""
    if _is_reviewer(principal):
        return
    if submission.submitted_by == principal.user_id and S(submission.workflow_status) not in (
        S.UNDER_HUMAN_REVIEW,
        S.REVIEWED,
        S.VERIFIED,
        S.REJECTED,
    ):
        if any(role in EVIDENCE_SUBMITTER_ROLES for role in principal.roles):
            return
    raise AppError("forbidden", "You cannot change this submission.", 403)

def _election(directory: DirectoryRepository, election_id: uuid.UUID) -> Election:
    election = directory.get_election(election_id)
    if election is None:
        raise AppError("unknown_election", "The election is not recognised.", 422)
    return election

def _polling_unit(directory: DirectoryRepository, polling_unit_id: uuid.UUID) -> PollingUnitDetail:
    unit = directory.get_polling_unit(polling_unit_id)
    if unit is None:
        raise AppError("unknown_polling_unit", "The polling unit is not recognised.", 422)
    return unit

def _election_ref(directory: DirectoryRepository, election_id: uuid.UUID) -> ElectionRef:
    election = directory.get_election(election_id)
    if election is None:
        return ElectionRef(id=election_id, name="Unknown election", is_demo=False)
    return ElectionRef(id=election.id, name=election.name, is_demo=election.is_demo)

def _unit_ref(directory: DirectoryRepository, submission: EvidenceSubmission) -> PollingUnitRef:
    unit = directory.get_polling_unit(submission.polling_unit_id)
    if unit is None:
        code = str(submission.provenance.get("polling_unit_code", "unknown"))
        return PollingUnitRef(
            id=submission.polling_unit_id,
            code=code,
            name="Unknown polling unit",
            state="",
            lga="",
            ward="",
        )
    return PollingUnitRef(
        id=unit.id,
        code=unit.code,
        name=unit.name,
        state=unit.state.name,
        lga=unit.lga.name,
        ward=unit.ward.name,
    )

def _summary(
    submission: EvidenceSubmission, directory: DirectoryRepository, principal: Principal
) -> dict[str, Any]:
    return {
        "id": submission.id,
        "election": _election_ref(directory, submission.election_id),
        "polling_unit": _unit_ref(directory, submission),
        "status": submission.workflow_status,
        "status_changed_at": submission.status_changed_at,
        "captured_at": submission.captured_at,
        "received_at": submission.received_at,
        "original_sha256": submission.original_sha256,
        "is_mine": submission.submitted_by == principal.user_id,
        "submitted_by": submission.submitted_by if _is_staff(principal) else None,
    }

def _image_view(image: EvidenceImage) -> EvidenceImageView:
    return EvidenceImageView(
        id=image.id,
        kind=image.kind,
        content_type=image.content_type,
        byte_size=image.byte_size,
        width=image.width,
        height=image.height,
        sha256=image.sha256,
        derived_from_id=image.derived_from_id,
        processing_steps=image.processing_steps,
        created_at=image.created_at,
    )

def _allowed_actions(submission: EvidenceSubmission, principal: Principal) -> list[str]:
    current = S(submission.workflow_status)
    actions: list[str] = []
    try:
        _require_editor(submission, principal)
        can_edit = True
    except AppError:
        can_edit = False
    if can_edit and current in workflow.PROCESSABLE:
        actions.append("process")
    if can_edit and current in workflow.EDITABLE:
        actions.append("correct")
    if can_edit and current in workflow.VALIDATABLE:
        actions.append("validate")
    if _is_reviewer(principal) and submission.submitted_by != principal.user_id:
        if current in workflow.REVIEWABLE:
            actions.append("start_review")
        if current in (S.UNDER_HUMAN_REVIEW, S.REVIEWED):
            actions += ["approve", "reject", "request_correction"]
    return actions

def _detail(
    db: Session,
    submission: EvidenceSubmission,
    directory: DirectoryRepository,
    principal: Principal,
) -> EvidenceDetail:
    provenance = dict(submission.provenance)
    if not _is_staff(principal) and submission.submitted_by != principal.user_id:
        provenance = {}
    return EvidenceDetail(
        **_summary(submission, directory, principal),
        template_id=submission.template_id,
        provenance=provenance,
        processing_error=submission.processing_error,
        images=[_image_view(i) for i in service.images(db, submission.id)],
        allowed_actions=_allowed_actions(submission, principal),
    )

@router.post("", response_model=SubmissionReceipt, status_code=status.HTTP_201_CREATED)
async def submit_evidence(
    request: Request,
    response: Response,
    principal: Submitter,
    db: Db,
    directory: Directory,
    storage: Storage,
    settings: AppSettings,
    file: Annotated[UploadFile, File(description="Result sheet photo: JPEG, PNG or WebP")],
    election_id: Annotated[uuid.UUID, Form()],
    polling_unit_id: Annotated[uuid.UUID, Form()],
    idempotency_key: Annotated[uuid.UUID, Header(alias="Idempotency-Key")],
    captured_at: Annotated[datetime | None, Form()] = None,
    capture_source: Annotated[Literal["camera", "upload"], Form()] = "upload",
    client_sha256: Annotated[
        str | None, Header(alias="X-Content-SHA256", pattern=r"^[A-Fa-f0-9]{64}$")
    ] = None,
) -> SubmissionReceipt:
    allowed, retry_after = _upload_limiter.check(str(principal.user_id))
    if not allowed:
        raise AppError(
            "rate_limited",
            "Too many uploads. Please wait and try again.",
            429,
            details={"retry_after_seconds": retry_after},
        )
    declared_length = request.headers.get("content-length")
    if (
        declared_length
        and declared_length.isdigit()
        and (int(declared_length) > settings.evidence_max_bytes + _MULTIPART_OVERHEAD)
    ):
        raise AppError("file_too_large", "The file is larger than the allowed size.", 413)

    election = _election(directory, election_id)
    unit = _polling_unit(directory, polling_unit_id)
    if captured_at is not None:
        aware = captured_at if captured_at.tzinfo else captured_at.replace(tzinfo=UTC)
        if aware > datetime.now(UTC).replace(microsecond=0) + _CLOCK_SKEW:
            raise AppError("invalid_capture_time", "The capture time is in the future.", 422)
        captured_at = aware.astimezone(UTC)

    data = await file.read(settings.evidence_max_bytes + 1)
    if len(data) > settings.evidence_max_bytes:
        raise AppError("file_too_large", "The file is larger than the allowed size.", 413)

    submission, created = service.ingest(
        db,
        storage,
        settings,
        principal,
        election,
        unit,
        Upload(
            data=data,
            filename=file.filename,
            content_type=file.content_type,
            idempotency_key=idempotency_key,
            captured_at=captured_at,
            client_sha256=client_sha256,
            client_info={
                "capture_source": capture_source,
                "user_agent": request.headers.get("user-agent", "")[:120],
            },
        ),
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return SubmissionReceipt(
        item=_detail(db, submission, directory, principal),
        created=created,
        message="Evidence received and fingerprinted."
        if created
        else "This evidence was already received; the existing record is returned.",
    )

@router.get("", response_model=EvidencePage)
def list_evidence(
    principal: AnyEvidenceUser,
    db: Db,
    directory: Directory,
    status_filter: Annotated[EvidenceStatus | None, Query(alias="status")] = None,
    queue: Annotated[Literal["review"] | None, Query()] = None,
    election_id: uuid.UUID | None = None,
    polling_unit_id: uuid.UUID | None = None,
    mine: bool = False,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> EvidencePage:
    if queue == "review" and not _is_staff(principal):
        raise AppError("forbidden", "You do not have access to this resource.", 403)
    query = select(EvidenceSubmission)
    if mine or not _is_staff(principal):
        query = query.where(EvidenceSubmission.submitted_by == principal.user_id)
    if status_filter is not None:
        query = query.where(EvidenceSubmission.workflow_status == status_filter)
    if queue == "review":
        query = query.where(EvidenceSubmission.workflow_status.in_(REVIEW_QUEUE))
    if election_id is not None:
        query = query.where(EvidenceSubmission.election_id == election_id)
    if polling_unit_id is not None:
        query = query.where(EvidenceSubmission.polling_unit_id == polling_unit_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    order = (
        EvidenceSubmission.status_changed_at.asc()
        if queue == "review"
        else EvidenceSubmission.received_at.desc()
    )
    rows = db.scalars(query.order_by(order).offset((page - 1) * page_size).limit(page_size))
    return EvidencePage(
        items=[EvidenceSummary(**_summary(row, directory, principal)) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=max(1, math.ceil(total / page_size)),
    )

@router.get("/{submission_id}", response_model=EvidenceDetail)
def get_evidence(
    submission_id: uuid.UUID, principal: AnyEvidenceUser, db: Db, directory: Directory
) -> EvidenceDetail:
    return _detail(db, _load(db, submission_id, principal), directory, principal)

@router.get("/{submission_id}/image", response_class=Response)
def get_evidence_image(
    submission_id: uuid.UUID,
    principal: AnyEvidenceUser,
    db: Db,
    storage: Storage,
    variant: Literal["original", "processed"] = "original",
) -> Response:
    submission = _load(db, submission_id, principal)
    if variant == "original":
        data = service.verify_original(db, storage, submission, principal.user_id)
        image = service.original_image(db, submission.id)
    else:
        image = next(
            (
                i
                for i in reversed(service.images(db, submission.id))
                if i.kind == EvidenceImageKind.PROCESSED
            ),
            None,
        )
        if image is None:
            raise AppError("not_found", "No processed image exists yet.", 404)
        data = read_verified(storage, image.storage_path, image.sha256)
    return Response(
        content=data,
        media_type=image.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": "inline",
            "X-Content-SHA256": image.sha256,
            "Content-Security-Policy": "default-src 'none'",
        },
    )

@router.get("/{submission_id}/integrity", response_model=IntegrityReport)
def get_integrity(
    submission_id: uuid.UUID, principal: AnyEvidenceUser, db: Db, storage: Storage
) -> IntegrityReport:
    submission = _load(db, submission_id, principal)
    problem: str | None = None
    try:
        service.verify_original(db, storage, submission, principal.user_id)
        verified = True
    except IntegrityError:
        verified, problem = False, "fingerprint_mismatch"
    except AppError as exc:
        verified, problem = False, exc.code
    chain = verify_chain(load_chain(db, submission.id))
    validation = service.latest_validation(db, submission.id)
    current_hash = service.current_result_hash(db, submission)
    return IntegrityReport(
        submission_id=submission.id,
        original_sha256=submission.original_sha256,
        original_verified=verified,
        original_problem=problem,
        checked_at=datetime.now(UTC),
        received_at=submission.received_at,
        captured_at=submission.captured_at,
        images=[_image_view(i) for i in service.images(db, submission.id)],
        current_result_hash=current_hash,
        validated_result_hash=validation.result_hash if validation else None,
        result_hash_matches_validation=(
            None
            if validation is None or current_hash is None
            else validation.result_hash == current_hash
        ),
        audit_chain_valid=chain.valid,
        audit_chain_length=chain.length,
        audit_head_hash=chain.head_hash,
    )

@router.post("/{submission_id}/process", response_model=ExtractionView)
def process_evidence(
    submission_id: uuid.UUID,
    principal: AnyEvidenceUser,
    db: Db,
    directory: Directory,
    storage: Storage,
    provider: Ocr,
    settings: AppSettings,
) -> ExtractionView:
    submission = _load(db, submission_id, principal)
    _require_editor(submission, principal)
    election = _election(directory, submission.election_id)
    service.process(db, storage, provider, settings, submission, election, principal)
    return _extraction_view(db, submission, election, settings)

def _extraction_view(
    db: Session, submission: EvidenceSubmission, election: Election, settings: Settings
) -> ExtractionView:
    extraction = service.latest_extraction(db, submission.id)
    if extraction is None:
        raise AppError("not_found", "This evidence has not been processed yet.", 404)
    template = get_template(extraction.template_id)
    labels = field_labels(template, election.parties)
    history = service.field_history(db, extraction.id)
    by_key: dict[str, list] = {}
    for row in history:
        by_key.setdefault(row.field_key, []).append(row)
    fields: list[ExtractedField] = []
    for key, meta in labels.items():
        rows = sorted(by_key.get(key, []), key=lambda r: r.version)
        if not rows:
            continue
        current, first = rows[-1], rows[0]
        fields.append(
            ExtractedField(
                field_key=key,
                label=meta["label"],
                kind=meta["kind"],
                required=meta["required"],
                value=service.field_value(current),
                origin=current.origin,
                confidence=current.confidence,
                source_text=current.source_text,
                bbox=current.bbox,
                requires_review=current.requires_review,
                review_reasons=current.review_reasons,
                version=current.version,
                ocr_value=service.field_value(first) if first.origin == "ocr" else None,
                ocr_confidence=first.confidence if first.origin == "ocr" else None,
                history=[
                    FieldVersion(
                        version=r.version,
                        origin=r.origin,
                        value=service.field_value(r),
                        confidence=r.confidence,
                        source_text=r.source_text,
                        requires_review=r.requires_review,
                        review_reasons=r.review_reasons,
                        reason=r.reason,
                        created_by=r.created_by,
                        created_at=r.created_at,
                    )
                    for r in rows
                ],
            )
        )
    return ExtractionView(
        id=extraction.id,
        status=extraction.status,
        provider=extraction.provider,
        provider_version=extraction.provider_version,
        template_id=template.id,
        template_notice=template.notice,
        mean_confidence=extraction.mean_confidence,
        confidence_threshold=settings.ocr_confidence_threshold,
        error=extraction.error,
        raw_text=extraction.raw_text,
        processed_image_id=extraction.image_id,
        created_at=extraction.created_at,
        fields=fields,
        attention_fields=[f.field_key for f in fields if f.requires_review],
    )

@router.get("/{submission_id}/extraction", response_model=ExtractionView)
def get_extraction(
    submission_id: uuid.UUID,
    principal: AnyEvidenceUser,
    db: Db,
    directory: Directory,
    settings: AppSettings,
) -> ExtractionView:
    submission = _load(db, submission_id, principal)
    return _extraction_view(db, submission, _election(directory, submission.election_id), settings)

@router.patch("/{submission_id}/extraction", response_model=ExtractionView)
def correct_extraction(
    submission_id: uuid.UUID,
    payload: ExtractionCorrectionIn,
    principal: AnyEvidenceUser,
    db: Db,
    directory: Directory,
    settings: AppSettings,
) -> ExtractionView:
    submission = _load(db, submission_id, principal)
    _require_editor(submission, principal)
    election = _election(directory, submission.election_id)
    service.correct(
        db,
        submission,
        election,
        principal,
        [
            Correction(field_key=c.field_key, value=c.value, reason=c.reason, confirm=c.confirm)
            for c in payload.corrections
        ],
    )
    return _extraction_view(db, submission, election, settings)

def _validation_view(db: Session, submission: EvidenceSubmission) -> ValidationView:
    validation = service.latest_validation(db, submission.id)
    if validation is None:
        raise AppError("not_found", "This evidence has not been validated yet.", 404)
    return ValidationView(
        id=validation.id,
        passed=validation.passed,
        result_hash=validation.result_hash,
        is_current=validation.result_hash == service.current_result_hash(db, submission),
        report=validation.report,
        created_at=validation.created_at,
    )

@router.post("/{submission_id}/validate", response_model=ValidationView)
def validate_evidence(
    submission_id: uuid.UUID,
    principal: AnyEvidenceUser,
    db: Db,
    directory: Directory,
    settings: AppSettings,
) -> ValidationView:
    submission = _load(db, submission_id, principal)
    _require_editor(submission, principal)
    election = _election(directory, submission.election_id)
    unit = _polling_unit(directory, submission.polling_unit_id)
    service.validate(db, submission, election, unit, principal, settings)
    return _validation_view(db, submission)

@router.get("/{submission_id}/validation", response_model=ValidationView)
def get_validation(submission_id: uuid.UUID, principal: AnyEvidenceUser, db: Db) -> ValidationView:
    return _validation_view(db, _load(db, submission_id, principal))

@router.get("/{submission_id}/comparisons", response_model=list[ComparisonView])
def get_comparisons(submission_id: uuid.UUID, principal: Staff, db: Db) -> list[ComparisonView]:
    submission = _load(db, submission_id, principal)
    latest = service.latest_comparison(db, submission.id)
    if latest is None:
        return []
    return [
        ComparisonView(
            id=latest.id,
            submission_ids=[uuid.UUID(i) for i in latest.submission_ids],
            has_conflicts=latest.has_conflicts,
            has_duplicates=latest.has_duplicates,
            report=latest.report,
            created_at=latest.created_at,
        )
    ]

@router.get("/{submission_id}/anomalies", response_model=AnomalyReport)
def get_anomalies(submission_id: uuid.UUID, principal: Staff, db: Db) -> AnomalyReport:
    submission = _load(db, submission_id, principal)
    validation = service.latest_validation(db, submission.id)
    current_run = validation.report.get("analysis_run_id") if validation else None
    rows: list[AnomalyAlert] = service.alerts(db, submission.id)
    return AnomalyReport(
        alerts=[
            AlertView(
                id=a.id,
                analysis_run_id=a.analysis_run_id,
                category=a.category,
                severity=a.severity,
                headline=a.headline,
                summary=a.summary,
                fields=a.fields,
                explanation=a.explanation,
                recommendation=a.recommendation,
                model_name=a.model_name,
                model_version=a.model_version,
                is_demo=a.is_demo,
                is_current=str(a.analysis_run_id) == current_run,
                created_at=a.created_at,
            )
            for a in rows
        ],
        statistical_analysis=validation.report.get("statistical_analysis") if validation else None,
    )

@router.get("/{submission_id}/audit", response_model=AuditTrail)
def get_audit(submission_id: uuid.UUID, principal: AnyEvidenceUser, db: Db) -> AuditTrail:
    submission = _load(db, submission_id, principal)
    events = load_chain(db, submission.id)
    chain = verify_chain(events)
    staff = _is_staff(principal)

    def actor(actor_id: uuid.UUID | None) -> str:
        if actor_id is None:
            return "system"
        if actor_id == principal.user_id:
            return "you"
        return "staff" if actor_id != submission.submitted_by else "submitter"

    return AuditTrail(
        events=[
            AuditEventView(
                id=e.id,
                sequence=e.sequence,
                action=e.action,
                actor=actor(e.actor_id),
                # Submitters do not see reviewer account identifiers.
                actor_id=e.actor_id if staff else None,
                created_at=e.created_at,
                details=e.details,
                previous_hash=e.previous_hash,
                event_hash=e.event_hash,
            )
            for e in events
        ],
        chain_valid=chain.valid,
        head_hash=chain.head_hash,
        broken_at_sequence=chain.broken_at_sequence,
        problem=chain.problem,
    )

def _review_view(row: Any) -> ReviewView:
    return ReviewView(
        id=row.id,
        reviewer_id=row.reviewer_id,
        decision=row.decision,
        notes=row.notes,
        result_hash=row.result_hash,
        created_at=row.created_at,
    )

@router.post("/{submission_id}/review", response_model=ReviewOutcome)
def review_evidence(
    submission_id: uuid.UUID,
    payload: ReviewIn,
    principal: Reviewer,
    db: Db,
    settings: AppSettings,
) -> ReviewOutcome:
    submission = _load(db, submission_id, principal)
    row = service.review(db, submission, principal, payload.action, payload.notes, settings)
    current_hash = service.current_result_hash(db, submission)
    approvals = service.approvals_for(db, submission, current_hash) if current_hash else []
    return ReviewOutcome(
        review=_review_view(row),
        status=submission.workflow_status,
        approvals=len(approvals),
        approvals_required=settings.verification_required_approvals,
    )

@router.get("/{submission_id}/reviews", response_model=ReviewHistory)
def get_reviews(
    submission_id: uuid.UUID, principal: Staff, db: Db, settings: AppSettings
) -> ReviewHistory:
    submission = _load(db, submission_id, principal)
    current_hash = service.current_result_hash(db, submission)
    approvals = service.approvals_for(db, submission, current_hash) if current_hash else []
    return ReviewHistory(
        reviews=[_review_view(r) for r in service.reviews(db, submission.id)],
        approvals=len(approvals),
        approvals_required=settings.verification_required_approvals,
    )
