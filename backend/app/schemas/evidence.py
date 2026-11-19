"""Evidence API models. Clients never send workflow statuses: status changes happen
only through processing, validation and review actions on the server."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, Field, StrictInt, StrictStr

from app.db.enums import (
    AlertCategory,
    AlertSeverity,
    EvidenceImageKind,
    EvidenceStatus,
    ExtractionStatus,
    FieldOrigin,
    ReviewDecision,
)
from app.schemas.common import ApiModel


def _as_utc(value: datetime) -> datetime:
    # SQLite returns naive values; everything is stored in UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


UtcDateTime = Annotated[datetime, AfterValidator(_as_utc)]

STATUS_NOTICE = (
    "VoteTrace statuses describe this platform's evidence checks and human review. "
    "They are not INEC declarations."
)


class LocationLabel(ApiModel):
    id: uuid.UUID
    name: str


class PollingUnitRef(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    state: str
    lga: str
    ward: str


class ElectionRef(ApiModel):
    id: uuid.UUID
    name: str
    is_demo: bool


class EvidenceSummary(ApiModel):
    id: uuid.UUID
    election: ElectionRef
    polling_unit: PollingUnitRef
    status: EvidenceStatus
    status_changed_at: UtcDateTime
    captured_at: UtcDateTime | None
    received_at: UtcDateTime
    original_sha256: str
    is_mine: bool
    # Internal account identifier; only staff receive it, never public viewers.
    submitted_by: uuid.UUID | None = None


class EvidenceImageView(ApiModel):
    id: uuid.UUID
    kind: EvidenceImageKind
    content_type: str
    byte_size: int
    width: int
    height: int
    sha256: str
    derived_from_id: uuid.UUID | None
    processing_steps: list[dict[str, Any]] | None
    created_at: UtcDateTime


class EvidenceDetail(EvidenceSummary):
    template_id: str
    provenance: dict[str, Any]
    processing_error: str | None
    images: list[EvidenceImageView]
    allowed_actions: list[str]
    status_notice: str = STATUS_NOTICE


class SubmissionReceipt(ApiModel):
    item: EvidenceDetail
    created: bool
    message: str


class EvidencePage(ApiModel):
    items: list[EvidenceSummary]
    page: int
    page_size: int
    total: int
    total_pages: int
    status_notice: str = STATUS_NOTICE


class FieldVersion(ApiModel):
    version: int
    origin: FieldOrigin
    value: int | str | None
    confidence: float | None
    source_text: str | None
    requires_review: bool
    review_reasons: list[str]
    reason: str | None
    created_by: uuid.UUID | None
    created_at: UtcDateTime


class ExtractedField(ApiModel):
    field_key: str
    label: str
    kind: Literal["integer", "text"]
    required: bool
    value: int | str | None
    origin: FieldOrigin
    confidence: float | None
    source_text: str | None
    bbox: dict[str, int] | None
    requires_review: bool
    review_reasons: list[str]
    version: int
    ocr_value: int | str | None
    ocr_confidence: float | None
    history: list[FieldVersion]


class ExtractionView(ApiModel):
    id: uuid.UUID
    status: ExtractionStatus
    provider: str
    provider_version: str | None
    template_id: str
    template_notice: str
    mean_confidence: float | None
    confidence_threshold: float
    error: str | None
    raw_text: str | None
    processed_image_id: uuid.UUID | None
    created_at: UtcDateTime
    fields: list[ExtractedField]
    attention_fields: list[str]
    disclaimer: str = (
        "OCR output is a draft. Low-confidence or flagged values must be checked against "
        "the original image by a person."
    )


class FieldCorrectionIn(ApiModel):
    field_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*(:[A-Z0-9]+)?$")
    value: StrictInt | StrictStr | None = Field(default=None)
    reason: str | None = Field(default=None, max_length=1000)
    # Confirm the current value as correct without changing it.
    confirm: bool = False


class ExtractionCorrectionIn(ApiModel):
    corrections: list[FieldCorrectionIn] = Field(min_length=1, max_length=60)


class ValidationView(ApiModel):
    id: uuid.UUID
    passed: bool
    result_hash: str
    is_current: bool
    report: dict[str, Any]
    created_at: UtcDateTime


class ComparisonView(ApiModel):
    id: uuid.UUID
    submission_ids: list[uuid.UUID]
    has_conflicts: bool
    has_duplicates: bool
    report: dict[str, Any]
    created_at: UtcDateTime


class AlertView(ApiModel):
    id: uuid.UUID
    analysis_run_id: uuid.UUID
    category: AlertCategory
    severity: AlertSeverity
    headline: str
    summary: str
    fields: list[str]
    explanation: dict[str, Any]
    recommendation: str
    model_name: str
    model_version: str
    is_demo: bool
    is_current: bool
    created_at: UtcDateTime


class AnomalyReport(ApiModel):
    alerts: list[AlertView]
    statistical_analysis: dict[str, Any] | None
    disclaimer: str = (
        "VoteTrace AI flags patterns for human review. It does not determine fraud, reject "
        "results or change values."
    )


class AuditEventView(ApiModel):
    id: uuid.UUID
    sequence: int
    action: str
    actor: str
    actor_id: uuid.UUID | None
    created_at: UtcDateTime
    details: dict[str, Any]
    previous_hash: str
    event_hash: str


class AuditTrail(ApiModel):
    events: list[AuditEventView]
    chain_valid: bool
    head_hash: str | None
    broken_at_sequence: int | None
    problem: str | None
    notice: str = (
        "The audit chain is tamper-evident: altering or removing an event breaks the chain. "
        "It does not stop a privileged database administrator from rewriting history."
    )


class IntegrityReport(ApiModel):
    submission_id: uuid.UUID
    original_sha256: str
    original_verified: bool
    original_problem: str | None
    checked_at: UtcDateTime
    received_at: UtcDateTime
    captured_at: UtcDateTime | None
    images: list[EvidenceImageView]
    current_result_hash: str | None
    validated_result_hash: str | None
    result_hash_matches_validation: bool | None
    audit_chain_valid: bool
    audit_chain_length: int
    audit_head_hash: str | None
    hash_notes: dict[str, str] = {
        "original_sha256": "SHA-256 of the exact uploaded image bytes.",
        "result_hash": "SHA-256 of the canonical structured result (field values only).",
        "audit_head_hash": "Hash of the latest audit event; each event hashes the previous one.",
    }


class ReviewIn(ApiModel):
    action: Literal["start", "approve", "reject", "request_correction"]
    notes: str | None = Field(default=None, max_length=4000)


class ReviewView(ApiModel):
    id: uuid.UUID
    reviewer_id: uuid.UUID
    decision: ReviewDecision
    notes: str | None
    result_hash: str | None
    created_at: UtcDateTime


class ReviewOutcome(ApiModel):
    review: ReviewView
    status: EvidenceStatus
    approvals: int
    approvals_required: int
    status_notice: str = STATUS_NOTICE


class ReviewHistory(ApiModel):
    reviews: list[ReviewView]
    approvals: int
    approvals_required: int
