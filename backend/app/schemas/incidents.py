import re
import uuid
from datetime import date
from typing import Any, Literal

from pydantic import Field, field_validator

from app.db.enums import IncidentCategory, IncidentSeverity, IncidentStatus
from app.schemas.common import ApiModel
from app.schemas.evidence import UtcDateTime

Band = Literal[
    "reported", "under_review", "corroborated", "verified", "inconclusive", "not_substantiated"
]
ReporterKind = Literal["anonymous", "protected", "account"]

INCIDENT_NOTICE = (
    "Incident reports are allegations made by members of the public. A report is not an "
    "established fact until VoteTrace reviewers verify it, and verification is not a legal "
    "or official finding."
)
PRIVACY_NOTICE = (
    "VoteTrace does not store your IP address, device identifiers or telephone number with "
    "a report, and removes location and camera details from photos. Phone numbers and "
    "e-mail addresses typed into the description are masked. If you are signed in, your "
    "account is linked to the report; choose protected reporting to hide it from reviewers. "
    "Your network provider and our hosting provider can still see that a connection was made."
)

_REF = r"^[A-Za-z0-9_:\-./ ]{1,120}$"


class LocationName(ApiModel):
    id: uuid.UUID
    name: str
    code: str | None = None


class IncidentReceipt(ApiModel):
    id: uuid.UUID
    reference: str
    status: IncidentStatus
    band: Band
    received_at: UtcDateTime
    created: bool
    duplicate: bool
    personal_data_redacted: bool
    attachment_stored: bool
    notice: str = INCIDENT_NOTICE
    privacy_notice: str = PRIVACY_NOTICE


class IncidentTrack(ApiModel):
    reference: str
    band: Band
    band_label: str
    received_at: UtcDateTime
    last_updated_at: UtcDateTime
    public_summary: str | None
    notice: str = INCIDENT_NOTICE


class IncidentSummary(ApiModel):
    id: uuid.UUID
    reference: str
    election_id: uuid.UUID
    category: IncidentCategory
    reported_category: IncidentCategory
    severity: IncidentSeverity
    status: IncidentStatus
    band: Band
    state: LocationName
    lga: LocationName
    ward: LocationName | None
    polling_unit: LocationName | None
    occurred_at: UtcDateTime
    time_is_approximate: bool
    received_at: UtcDateTime
    status_changed_at: UtcDateTime
    excerpt: str
    has_attachment: bool
    possible_duplicate_of: str | None
    similar_count: int
    missing_count: int
    reporter: ReporterKind
    is_public: bool


class IncidentPage(ApiModel):
    items: list[IncidentSummary]
    page: int
    page_size: int
    total: int
    total_pages: int
    notice: str = INCIDENT_NOTICE
    generated_at: UtcDateTime


class AttachmentView(ApiModel):
    id: uuid.UUID
    content_type: str
    byte_size: int
    width: int
    height: int
    sha256: str
    created_at: UtcDateTime


class ReviewView(ApiModel):
    id: uuid.UUID
    reviewer_id: uuid.UUID
    previous_status: IncidentStatus
    new_status: IncidentStatus
    reason: str
    evidence_refs: list[str]
    category_from: IncidentCategory | None
    category_to: IncidentCategory | None
    severity_from: IncidentSeverity | None
    severity_to: IncidentSeverity | None
    public_summary: str | None
    published: bool
    created_at: UtcDateTime


class IncidentDetail(IncidentSummary):
    description: str
    latitude: float | None
    longitude: float | None
    triage: dict[str, Any]
    attachments: list[AttachmentView]
    reviews: list[ReviewView]
    public_summary: str | None
    published_at: UtcDateTime | None
    resolution_basis: IncidentStatus | None
    reporter_user_id: uuid.UUID | None
    allowed_transitions: list[IncidentStatus]
    can_review: bool
    channel: str


class IncidentReviewIn(ApiModel):
    new_status: IncidentStatus
    reason: str = Field(min_length=10, max_length=2000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=10)
    category: IncidentCategory | None = None
    severity: IncidentSeverity | None = None
    publish: bool | None = None
    public_summary: str | None = Field(default=None, min_length=20, max_length=500)

    @field_validator("evidence_refs")
    @classmethod
    def clean_refs(cls, refs: list[str]) -> list[str]:
        cleaned = [ref.strip() for ref in refs if ref.strip()]
        for ref in cleaned:
            if not re.fullmatch(_REF, ref):
                raise ValueError("Evidence references may use letters, digits and - _ : . /")
        return list(dict.fromkeys(cleaned))


class CountItem(ApiModel):
    key: str
    label: str
    count: int


class AreaCount(ApiModel):
    id: uuid.UUID
    name: str
    parent: str | None = None
    count: int


class TimelinePoint(ApiModel):
    period: str
    count: int


class IncidentStats(ApiModel):
    total: int
    awaiting_review: int
    under_investigation: int
    verified: int
    unverified: int
    inconclusive: int
    rejected: int
    resolved: int
    possible_duplicates: int
    critical_open: int
    by_category: list[CountItem]
    by_status: list[CountItem]
    by_severity: list[CountItem]
    by_band: list[CountItem]
    by_state: list[AreaCount]
    by_lga: list[AreaCount]
    timeline_bucket: Literal["hour", "day"]
    timeline: list[TimelinePoint]
    notice: str = INCIDENT_NOTICE
    generated_at: UtcDateTime


class PublicIncident(ApiModel):
    """Reviewer-approved public information only. No reporter, no original text."""

    category: IncidentCategory
    state: str
    lga: str
    occurred_on: date
    summary: str
    published_at: UtcDateTime


class PublicIncidentSummary(ApiModel):
    election_id: uuid.UUID
    by_band: list[CountItem]
    published: list[PublicIncident]
    notice: str = INCIDENT_NOTICE
    demo_label: str | None
    generated_at: UtcDateTime
