import uuid
from datetime import datetime
from typing import Literal

from app.db.enums import EvidenceStatus, PollingUnitResultStatus
from app.schemas.common import ApiModel, DataSource
from app.schemas.evidence import UtcDateTime

Level = Literal["national", "state", "lga", "ward", "polling_unit"]
DataStatus = Literal["demonstration", "live"]

CIVIC_NOTICE = (
    "VoteTrace provides independent civic verification of polling-unit evidence. These "
    "figures are not INEC declarations, are not legally binding, and do not name a winner."
)
DEMO_LABEL = "Sample data. Not an official election result."
PARTIAL_NOTICE = (
    "Totals cover only the polling units counted in each stream. Partial coverage is "
    "not a complete election result."
)


class ElectionRef(ApiModel):
    id: uuid.UUID
    name: str
    election_label: str
    is_demo: bool


class AreaRef(ApiModel):
    level: Level
    id: uuid.UUID | None
    name: str
    code: str | None = None


class Coverage(ApiModel):
    expected_polling_units: int
    polling_units_with_submissions: int
    reporting_polling_units: int
    verified_polling_units: int
    pending_polling_units: int
    flagged_polling_units: int
    conflict_polling_units: int
    anomaly_polling_units: int
    submission_count: int
    independent_submission_count: int
    rejected_submission_count: int
    incomplete_registry_entries: int
    # Percentages of expected polling units; null when the area expects none.
    reporting_coverage_pct: float | None
    verification_coverage_pct: float | None
    reporting_label: str
    verification_label: str


class AreaSummary(ApiModel):
    area: AreaRef
    iso_code: str | None = None
    coverage: Coverage
    last_updated_at: UtcDateTime | None


class PartyTotal(ApiModel):
    code: str
    name: str
    votes: int
    # Share of the party votes counted in this stream for this area, not of all votes cast.
    share_pct: float | None


class StreamTotals(ApiModel):
    stream: Literal["reported", "verified"]
    description: str
    polling_units_included: int
    expected_polling_units: int
    registered_voters: int
    accredited_voters: int
    total_valid_votes: int
    rejected_votes: int
    total_votes_cast: int
    parties: list[PartyTotal]
    share_basis: str


class AlertSummary(ApiModel):
    kind: Literal[
        "unresolved_discrepancies", "records_requiring_review", "unusual_patterns", "incomplete"
    ]
    count: int
    title: str
    description: str
    href: str | None = None


class Provenance(ApiModel):
    aggregation_level: Level
    registry_source: DataSource
    method: str
    source_records_path: str


class AreaResponse(ApiModel):
    election: ElectionRef
    level: Level
    summary: AreaSummary
    breadcrumbs: list[AreaRef]
    reported: StreamTotals
    verified: StreamTotals
    child_level: Level | None
    children: list[AreaSummary]
    child_areas_reporting: int
    child_areas_outstanding: int
    alerts: list[AlertSummary]
    data_status: DataStatus
    demo_label: str | None
    notice: str
    partial_notice: str
    provenance: Provenance
    generated_at: UtcDateTime


class AreaListResponse(ApiModel):
    election: ElectionRef
    level: Level
    items: list[AreaSummary]
    page: int
    page_size: int
    total: int
    total_pages: int
    data_status: DataStatus
    demo_label: str | None
    notice: str
    generated_at: UtcDateTime


class PartyBreakdown(ApiModel):
    area: AreaRef
    reported: StreamTotals
    verified: StreamTotals


class PartyResultsResponse(ApiModel):
    election: ElectionRef
    area: AreaRef
    reported: StreamTotals
    verified: StreamTotals
    breakdown_level: Level | None
    breakdown: list[PartyBreakdown]
    data_status: DataStatus
    demo_label: str | None
    notice: str
    partial_notice: str
    generated_at: UtcDateTime


class PollingUnitRow(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    ward: AreaRef
    lga: AreaRef
    state: AreaRef
    status: PollingUnitResultStatus
    submission_count: int
    accepted_count: int
    independent_count: int
    distinct_results: int
    has_flagged: bool
    has_anomaly: bool
    reported_result_hash: str | None
    verified_result_hash: str | None
    registry_incomplete: bool
    revision: int | None
    updated_at: UtcDateTime | None


class PollingUnitPage(ApiModel):
    election: ElectionRef
    items: list[PollingUnitRow]
    page: int
    page_size: int
    total: int
    total_pages: int
    data_status: DataStatus
    demo_label: str | None
    notice: str
    generated_at: UtcDateTime


class SourceRecord(ApiModel):
    """A submission as the public may see it: no submitter, no image, no storage path."""

    submission_id: uuid.UUID
    workflow_status: EvidenceStatus
    received_at: UtcDateTime
    result_fingerprint: str | None
    validation_passed: bool | None
    agrees_with_reported: bool | None
    contributes: bool


class VerificationReport(ApiModel):
    status: PollingUnitResultStatus
    required_approvals: int
    approvals_on_verified_result: int
    verified_at: UtcDateTime | None
    checks_passed: int
    checks_failed: int
    warnings: int
    disclaimer: str


class PollingUnitResultResponse(ApiModel):
    election: ElectionRef
    unit: PollingUnitRow
    breadcrumbs: list[AreaRef]
    reported: StreamTotals
    verified: StreamTotals
    verification: VerificationReport
    source_records: list[SourceRecord]
    data_status: DataStatus
    demo_label: str | None
    notice: str
    generated_at: UtcDateTime


class ProgressPoint(ApiModel):
    at: UtcDateTime
    reporting_polling_units: int
    verified_polling_units: int


class ProgressResponse(ApiModel):
    election: ElectionRef
    area: AreaRef
    expected_polling_units: int
    bucket: Literal["hour"]
    points: list[ProgressPoint]
    description: str
    data_status: DataStatus
    demo_label: str | None
    generated_at: UtcDateTime


class RebuildResult(ApiModel):
    election_id: uuid.UUID
    polling_units_changed: int
    generated_at: datetime
