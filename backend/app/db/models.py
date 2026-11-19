"""Persistence model for VoteTrace.

These tables describe the domain. Evidence, extraction, validation and review
rows are written only by the server-side evidence workflow (app/evidence);
history tables are append-only. No public route writes to them.

Built-in account passwords are stored only as scrypt hashes in `user_credentials`.
Directory, election and evidence tables use portable types and client-side defaults,
so the same model runs on Postgres and on the SQLite development store.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import (
    AlertCategory,
    AlertSeverity,
    ElectionStatus,
    EvidenceImageKind,
    EvidenceStatus,
    ExtractionStatus,
    FieldOrigin,
    IncidentCategory,
    IncidentSeverity,
    IncidentStatus,
    NoticeVerificationStatus,
    PollingUnitResultStatus,
    PollingUnitStatus,
    ResultSource,
    ResultStream,
    ReviewDecision,
    Role,
    UpdateCategory,
    UpdateVerificationStatus,
    VerificationStatus,
)


def _pg_enum(enum_type: type, name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        native_enum=True,
        values_callable=lambda members: [member.value for member in members],
    )


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _non_negative(column: str) -> CheckConstraint:
    return CheckConstraint(
        f"{column} IS NULL OR {column} >= 0",
        name=f"{column}_non_negative",
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )


class User(TimestampMixin, Base):
    """Account profile. Passwords for built-in accounts live in `user_credentials`."""

    __tablename__ = "users"
    __table_args__ = {"comment": "Profile mirror of auth.users. Passwords are not stored."}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )


class RoleAssignment(Base):
    """Durable role grant. Request-time authority is the signed app_metadata claim."""

    __tablename__ = "role_assignments"
    __table_args__ = (UniqueConstraint("user_id", "role"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[Role] = mapped_column(_pg_enum(Role, "app_role"))
    granted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )


class UserCredential(Base):
    """Password for a built-in account. Absent for users who sign in through Supabase."""

    __tablename__ = "user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Raised on every password change or reset; older tokens carry a lower number.
    token_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_sign_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Election(TimestampMixin, Base):
    __tablename__ = "elections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    election_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[ElectionStatus] = mapped_column(
        _pg_enum(ElectionStatus, "election_status"),
        default=ElectionStatus.SCHEDULED,
        server_default=ElectionStatus.SCHEDULED.value,
    )
    # Text printed on the result sheet, used to cross-check sheets against the election.
    election_label: Mapped[str] = mapped_column(String(200), nullable=False)
    template_id: Mapped[str] = mapped_column(String(80), nullable=False)
    # Parties on the ballot, [{"code": "...", "name": "..."}], in ballot order.
    parties: Mapped[list[dict[str, str]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=list, nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class State(Base):
    __tablename__ = "states"
    __table_args__ = (Index("uq_states_iso_code", "iso_code", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # ISO 3166-2 subdivision code (NG-LA, NG-FC, ...), the join key for boundary data.
    iso_code: Mapped[str | None] = mapped_column(String(8))


class Lga(Base):
    __tablename__ = "lgas"
    __table_args__ = (UniqueConstraint("state_id", "code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    state_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("states.id"), index=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class Ward(Base):
    __tablename__ = "wards"
    __table_args__ = (UniqueConstraint("lga_id", "code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lga_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lgas.id"), index=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class PollingUnit(Base):
    __tablename__ = "polling_units"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ward_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("wards.id"), index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address_description: Mapped[str | None] = mapped_column(Text)
    # WGS 84. On Postgres a trigger keeps the PostGIS `location` column in step.
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    registered_voters: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[PollingUnitStatus] = mapped_column(
        _pg_enum(PollingUnitStatus, "polling_unit_status"),
        default=PollingUnitStatus.PENDING_VERIFICATION,
        server_default=PollingUnitStatus.PENDING_VERIFICATION.value,
    )
    source_name: Mapped[str | None] = mapped_column(String(200))
    source_reference: Mapped[str | None] = mapped_column(String(200))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        _non_negative("registered_voters"),
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180", name="longitude_range"
        ),
    )


class PollingUnitNotice(Base):
    """Official notice about a polling unit (e.g. relocation). Entered by staff only.

    Crowd reports live in `relocation_reports` and are never copied here automatically.
    """

    __tablename__ = "polling_unit_notices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    polling_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("polling_units.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500))
    reference: Mapped[str | None] = mapped_column(String(200))
    new_location_description: Mapped[str | None] = mapped_column(Text)
    effective_date: Mapped[date | None] = mapped_column(Date)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verification_status: Mapped[NoticeVerificationStatus] = mapped_column(
        _pg_enum(NoticeVerificationStatus, "notice_verification_status")
    )
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )


class RelocationReport(Base):
    """Crowdsourced relocation report. Never authoritative on its own."""

    __tablename__ = "relocation_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    polling_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("polling_units.id"), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    reporter_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ElectionUpdate(Base):
    __tablename__ = "election_updates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[UpdateCategory] = mapped_column(_pg_enum(UpdateCategory, "update_category"))
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    reference: Mapped[str | None] = mapped_column(String(200))
    verification_status: Mapped[UpdateVerificationStatus] = mapped_column(
        _pg_enum(UpdateVerificationStatus, "update_verification_status")
    )
    polling_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("polling_units.id"), index=True
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    published_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )


# Evidence tables use portable types (Uuid, JSON→JSONB) and client-side defaults so
# the same model runs on Postgres and on the SQLite development store.
PortableJSON = JSON().with_variant(JSONB(), "postgresql")


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class EvidenceSubmission(Base):
    """A photographed result sheet submitted by an observer or party agent.

    `workflow_status` is VoteTrace's processing and review state, changed only by
    server-side workflow transitions. It is not an INEC declaration status.
    """

    __tablename__ = "evidence_submissions"
    __table_args__ = (
        UniqueConstraint("submitted_by", "idempotency_key", name="uq_evidence_idempotency"),
        Index("ix_evidence_election_polling_unit", "election_id", "polling_unit_id"),
        CheckConstraint("length(original_sha256) = 64", name="original_sha256_length"),
        {"comment": "Original image bytes live in a private bucket; see evidence_images."},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    election_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("elections.id"), nullable=False)
    polling_unit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("polling_units.id"), nullable=False, index=True
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    idempotency_key: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    template_id: Mapped[str] = mapped_column(String(80), nullable=False)
    workflow_status: Mapped[EvidenceStatus] = mapped_column(
        _pg_enum(EvidenceStatus, "evidence_status"),
        default=EvidenceStatus.RECEIVED,
        nullable=False,
        index=True,
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    # Device capture time (client-reported) and server receipt time are kept apart.
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    original_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provenance: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False, default=dict)
    processing_error: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class EvidenceImage(Base):
    """An original upload or a derivative. Originals are never modified or re-encoded."""

    __tablename__ = "evidence_images"
    __table_args__ = (
        Index(
            "uq_evidence_images_one_original",
            "submission_id",
            unique=True,
            postgresql_where=text("kind = 'original'"),
            sqlite_where=text("kind = 'original'"),
        ),
        CheckConstraint("length(sha256) = 64", name="image_sha256_length"),
        _non_negative("byte_size"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evidence_submissions.id"), nullable=False, index=True
    )
    kind: Mapped[EvidenceImageKind] = mapped_column(
        _pg_enum(EvidenceImageKind, "evidence_image_kind"), nullable=False
    )
    derived_from_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("evidence_images.id")
    )
    storage_bucket: Mapped[str] = mapped_column(String(120), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(60), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 64-bit difference hash (hex) for near-duplicate detection. Not a security hash.
    perceptual_hash: Mapped[str | None] = mapped_column(String(16), index=True)
    processing_steps: Mapped[list[dict[str, Any]] | None] = mapped_column(PortableJSON)
    created_at: Mapped[datetime] = _created_at()


class OcrExtraction(Base):
    """One immutable OCR run. Human corrections never modify it."""

    __tablename__ = "ocr_extractions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evidence_submissions.id"), nullable=False, index=True
    )
    image_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("evidence_images.id"))
    template_id: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    provider_version: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[ExtractionStatus] = mapped_column(
        _pg_enum(ExtractionStatus, "extraction_status"), nullable=False
    )
    raw_text: Mapped[str | None] = mapped_column(Text)
    tokens: Mapped[list[dict[str, Any]]] = mapped_column(PortableJSON, nullable=False, default=list)
    mean_confidence: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = _created_at()


class ExtractedResultField(Base):
    """A versioned field value. Version 1 is the OCR output; later versions are human
    corrections or confirmations. Rows are never updated; the effective value is the
    highest version per field."""

    __tablename__ = "extracted_result_fields"
    __table_args__ = (
        UniqueConstraint("extraction_id", "field_key", "version", name="uq_field_version"),
        CheckConstraint("value_int IS NULL OR value_int >= 0", name="field_value_non_negative"),
        CheckConstraint("version >= 1", name="field_version_positive"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ocr_extractions.id"), nullable=False, index=True
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evidence_submissions.id"), nullable=False, index=True
    )
    field_key: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[FieldOrigin] = mapped_column(_pg_enum(FieldOrigin, "field_origin"))
    value_int: Mapped[int | None] = mapped_column(Integer)
    value_text: Mapped[str | None] = mapped_column(String(120))
    confidence: Mapped[float | None] = mapped_column(Float)
    source_text: Mapped[str | None] = mapped_column(String(200))
    bbox: Mapped[dict[str, int] | None] = mapped_column(PortableJSON)
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_reasons: Mapped[list[str]] = mapped_column(PortableJSON, nullable=False, default=list)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = _created_at()


class ResultValidation(Base):
    """Deterministic arithmetic and consistency checks over one snapshot of values."""

    __tablename__ = "result_validations"
    __table_args__ = (CheckConstraint("length(result_hash) = 64", name="result_hash_length"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evidence_submissions.id"), nullable=False, index=True
    )
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ocr_extractions.id"), nullable=False
    )
    template_id: Mapped[str] = mapped_column(String(80), nullable=False)
    # SHA-256 of the canonical result representation. Distinct from image and audit hashes.
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    result_snapshot: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    report: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = _created_at()


class SubmissionComparison(Base):
    """Comparison of all submissions for one election and polling unit at a point in time."""

    __tablename__ = "submission_comparisons"
    __table_args__ = (
        Index("ix_comparisons_election_polling_unit", "election_id", "polling_unit_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    election_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    polling_unit_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    trigger_submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evidence_submissions.id"), nullable=False, index=True
    )
    submission_ids: Mapped[list[str]] = mapped_column(PortableJSON, nullable=False)
    has_conflicts: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_duplicates: Mapped[bool] = mapped_column(Boolean, nullable=False)
    report: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class AnomalyAlert(Base):
    """VoteTrace AI alert. Advisory only: it never changes values or decides outcomes."""

    __tablename__ = "anomaly_alerts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evidence_submissions.id"), nullable=False, index=True
    )
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    category: Mapped[AlertCategory] = mapped_column(_pg_enum(AlertCategory, "alert_category"))
    severity: Mapped[AlertSeverity] = mapped_column(_pg_enum(AlertSeverity, "alert_severity"))
    headline: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    fields: Mapped[list[str]] = mapped_column(PortableJSON, nullable=False, default=list)
    explanation: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _created_at()


class EvidenceReview(Base):
    """A human review action. Append-only."""

    __tablename__ = "evidence_reviews"

    id: Mapped[uuid.UUID] = _uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evidence_submissions.id"), nullable=False, index=True
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    decision: Mapped[ReviewDecision] = mapped_column(_pg_enum(ReviewDecision, "review_decision"))
    notes: Mapped[str | None] = mapped_column(Text)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    validation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("result_validations.id")
    )
    created_at: Mapped[datetime] = _created_at()


class PollingUnitResult(Base):
    """Derived aggregation state of one polling unit for one election.

    Recomputed by app/analytics from evidence submissions, validations and reviews in the
    same transaction as the change that caused it. Never written from a request body.
    One row per election and polling unit, so a unit is never counted twice."""

    __tablename__ = "polling_unit_results"
    __table_args__ = (
        UniqueConstraint("election_id", "polling_unit_id", name="uq_pu_result_unit"),
        Index("ix_pu_results_state", "election_id", "state_id"),
        Index("ix_pu_results_lga", "election_id", "lga_id"),
        Index("ix_pu_results_ward", "election_id", "ward_id"),
        Index("ix_pu_results_status", "election_id", "status"),
        _non_negative("submission_count"),
        _non_negative("accepted_count"),
        _non_negative("independent_count"),
        _non_negative("rejected_count"),
        CheckConstraint("revision >= 1", name="pu_result_revision_positive"),
        CheckConstraint(
            "status <> 'verified' OR verified_result_hash IS NOT NULL",
            name="pu_result_verified_has_hash",
        ),
        CheckConstraint(
            "status NOT IN ('reported', 'verified') OR reported_result_hash IS NOT NULL",
            name="pu_result_reported_has_hash",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    election_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("elections.id"), nullable=False)
    polling_unit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("polling_units.id"), nullable=False
    )
    # Stable registry identifiers, copied so each level is one indexed GROUP BY.
    ward_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    lga_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    state_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[PollingUnitResultStatus] = mapped_column(
        _pg_enum(PollingUnitResultStatus, "pu_result_status"), nullable=False
    )
    submission_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    independent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    distinct_results: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_anomaly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reported_result_hash: Mapped[str | None] = mapped_column(String(64))
    verified_result_hash: Mapped[str | None] = mapped_column(String(64))
    # Submission ids: every non-rejected submission, and those whose agreed values are used.
    source_submission_ids: Mapped[list[str]] = mapped_column(PortableJSON, nullable=False)
    contributing_submission_ids: Mapped[list[str]] = mapped_column(PortableJSON, nullable=False)
    first_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_submission_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PollingUnitResultMetric(Base):
    """One figure (party votes or a total) of one polling unit in one stream. Derived from
    PollingUnitResult and replaced with it. Level totals are SUM over these rows."""

    __tablename__ = "polling_unit_result_metrics"
    __table_args__ = (
        UniqueConstraint("result_id", "stream", "metric", name="uq_pu_metric"),
        Index("ix_pu_metrics_state", "election_id", "stream", "state_id"),
        Index("ix_pu_metrics_lga", "election_id", "stream", "lga_id"),
        Index("ix_pu_metrics_ward", "election_id", "stream", "ward_id"),
        CheckConstraint("value >= 0", name="pu_metric_value_non_negative"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    result_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("polling_unit_results.id"), nullable=False, index=True
    )
    election_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    polling_unit_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    ward_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    lga_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    state_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    stream: Mapped[ResultStream] = mapped_column(
        _pg_enum(ResultStream, "result_stream"), nullable=False
    )
    metric: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)


class ExtractedResultRecord(TimestampMixin, Base):
    """Figures recorded against a polling unit. Not writable by public clients."""

    __tablename__ = "extracted_result_records"
    __table_args__ = (
        _non_negative("accredited_voters"),
        _non_negative("ballot_papers_issued"),
        _non_negative("unused_ballots"),
        _non_negative("spoiled_ballots"),
        _non_negative("rejected_ballots"),
        _non_negative("total_valid_votes"),
        {"comment": "vote_counts is defined later. This table has no status column."},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    election_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("elections.id"), index=True)
    polling_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("polling_units.id"), index=True)
    evidence_submission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_submissions.id"), index=True
    )
    source: Mapped[ResultSource] = mapped_column(_pg_enum(ResultSource, "result_source"))
    accredited_voters: Mapped[int | None] = mapped_column(Integer)
    ballot_papers_issued: Mapped[int | None] = mapped_column(Integer)
    unused_ballots: Mapped[int | None] = mapped_column(Integer)
    spoiled_ballots: Mapped[int | None] = mapped_column(Integer)
    rejected_ballots: Mapped[int | None] = mapped_column(Integer)
    total_valid_votes: Mapped[int | None] = mapped_column(Integer)
    vote_counts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class VerificationRecord(Base):
    """Append-only decision. The current status is the latest row for a result."""

    __tablename__ = "verification_records"
    __table_args__ = {
        "comment": "Insert a new row to change status. Clients cannot update these rows."
    }

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    extracted_result_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extracted_result_records.id"), index=True
    )
    status: Mapped[VerificationStatus] = mapped_column(
        _pg_enum(VerificationStatus, "verification_status")
    )
    justification: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )


class AuditEvent(Base):
    """Append-only, hash-chained audit trail. Each entity has its own chain:
    `event_hash` covers the event and `previous_hash`, so editing or removing an
    earlier event breaks every later hash. Tamper-evident, not tamper-proof."""

    __tablename__ = "audit_events"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "sequence", name="uq_audit_chain_position"),
        CheckConstraint("length(event_hash) = 64", name="event_hash_length"),
        CheckConstraint("length(previous_hash) = 64", name="previous_hash_length"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    request_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )


class IncidentReport(Base):
    """An electoral incident as reported. An allegation, never an established fact.

    `reported_category` and `description` are the reporter's words and are never
    changed. `category`, `severity` and `status` are the current triage and review
    state, changed only by the server (triage) or by authorised reviewers. No IP
    address, device identifier or telephone number is stored."""

    __tablename__ = "incident_reports"
    __table_args__ = (
        Index("ix_incidents_election_status", "election_id", "status"),
        Index("ix_incidents_area", "election_id", "state_id", "lga_id"),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)", name="incident_latitude"
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="incident_longitude",
        ),
        CheckConstraint(
            "is_public = false OR public_summary IS NOT NULL", name="incident_public_has_summary"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Unguessable receipt shown to the reporter. Also lets them check progress.
    reference: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    election_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("elections.id"), nullable=False)
    reported_category: Mapped[IncidentCategory] = mapped_column(
        _pg_enum(IncidentCategory, "incident_category"), nullable=False
    )
    category: Mapped[IncidentCategory] = mapped_column(
        _pg_enum(IncidentCategory, "incident_category"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    state_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("states.id"), nullable=False)
    lga_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("lgas.id"), nullable=False)
    ward_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("wards.id"))
    polling_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("polling_units.id"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time_is_approximate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    status: Mapped[IncidentStatus] = mapped_column(
        _pg_enum(IncidentStatus, "incident_status"),
        nullable=False,
        default=IncidentStatus.RECEIVED,
        index=True,
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    # The decision a RESOLVED report was closed on (for example verified or unverified).
    resolution_basis: Mapped[IncidentStatus | None] = mapped_column(
        _pg_enum(IncidentStatus, "incident_status")
    )
    severity: Mapped[IncidentSeverity] = mapped_column(
        _pg_enum(IncidentSeverity, "incident_severity"), nullable=False, index=True
    )
    # Deterministic triage output: rules applied, keywords, missing information.
    triage: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False, default=dict)
    # Earliest similar report in the same area, if any. A signal for reviewers only.
    possible_duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("incident_reports.id")
    )
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    area_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    reporter_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    # When true the account link is kept only to stop self-review; it is never shown.
    identity_protected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    client_generated_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="web")
    # Text written by a reviewer for public display. The report itself is never public.
    public_summary: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class IncidentAttachment(Base):
    """A supporting photo, re-encoded without metadata (location, device) and kept in
    private storage. Never served to the public."""

    __tablename__ = "incident_attachments"
    __table_args__ = (
        CheckConstraint("length(sha256) = 64", name="incident_attachment_sha256_length"),
        _non_negative("byte_size"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("incident_reports.id"), nullable=False, index=True
    )
    storage_bucket: Mapped[str] = mapped_column(String(120), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(60), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = _created_at()


class IncidentReview(Base):
    """One reviewer decision on an incident. Append-only."""

    __tablename__ = "incident_reviews"

    id: Mapped[uuid.UUID] = _uuid_pk()
    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("incident_reports.id"), nullable=False, index=True
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    previous_status: Mapped[IncidentStatus] = mapped_column(
        _pg_enum(IncidentStatus, "incident_status"), nullable=False
    )
    new_status: Mapped[IncidentStatus] = mapped_column(
        _pg_enum(IncidentStatus, "incident_status"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # References to supporting material: evidence submission ids, update ids, notes.
    evidence_refs: Mapped[list[str]] = mapped_column(PortableJSON, nullable=False, default=list)
    category_from: Mapped[IncidentCategory | None] = mapped_column(
        _pg_enum(IncidentCategory, "incident_category")
    )
    category_to: Mapped[IncidentCategory | None] = mapped_column(
        _pg_enum(IncidentCategory, "incident_category")
    )
    severity_from: Mapped[IncidentSeverity | None] = mapped_column(
        _pg_enum(IncidentSeverity, "incident_severity")
    )
    severity_to: Mapped[IncidentSeverity | None] = mapped_column(
        _pg_enum(IncidentSeverity, "incident_severity")
    )
    public_summary: Mapped[str | None] = mapped_column(Text)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _created_at()


class SmsMessage(Base):
    """An inbound SMS query and the reply sent. The sender's number is stored only as
    a keyed hash. Rows are never updated."""

    __tablename__ = "sms_messages"
    __table_args__ = (
        UniqueConstraint("provider", "provider_message_id", name="uq_sms_provider_message"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    message_ref: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(100))
    sender_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    command: Mapped[str] = mapped_column(String(20), nullable=False)
    argument: Mapped[str | None] = mapped_column(String(40))
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    response_parts: Mapped[list[str]] = mapped_column(PortableJSON, nullable=False)
    received_at: Mapped[datetime] = _created_at()


class AppendOnlyViolationError(RuntimeError):
    pass


# History tables. The ORM refuses updates and deletes; migration 0002 adds matching
# Postgres triggers so raw SQL from the application role is refused too.
APPEND_ONLY_MODELS: tuple[type[Base], ...] = (
    EvidenceImage,
    OcrExtraction,
    ExtractedResultField,
    ResultValidation,
    SubmissionComparison,
    AnomalyAlert,
    EvidenceReview,
    VerificationRecord,
    AuditEvent,
    IncidentAttachment,
    IncidentReview,
    SmsMessage,
)


def _refuse_change(_mapper: object, _connection: object, target: Base) -> None:
    raise AppendOnlyViolationError(f"{type(target).__tablename__} rows are append-only")


for _model in APPEND_ONLY_MODELS:
    event.listen(_model, "before_update", _refuse_change)
    event.listen(_model, "before_delete", _refuse_change)
