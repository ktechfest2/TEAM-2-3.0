from enum import StrEnum

# Keep in sync with frontend/src/features/auth/roles.ts
# and frontend/src/features/verification/status.tsx.


class Role(StrEnum):
    OBSERVER = "observer"
    PARTY_AGENT = "party_agent"
    REVIEWER = "reviewer"
    AUDITOR = "auditor"
    ELECTION_ADMIN = "election_admin"
    SYSTEM_ADMIN = "system_admin"


# Roles allowed into the administrative console. Mirrors ADMIN_CONSOLE_ROLES.
ADMIN_CONSOLE_ROLES: tuple[Role, ...] = (
    Role.REVIEWER,
    Role.AUDITOR,
    Role.ELECTION_ADMIN,
    Role.SYSTEM_ADMIN,
)


class ElectionStatus(StrEnum):
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    CLOSED = "closed"


# Field roles that may submit evidence. Admin roles may also submit (for testing and
# supervised capture) but never review their own submissions.
EVIDENCE_SUBMITTER_ROLES: tuple[Role, ...] = (
    Role.OBSERVER,
    Role.PARTY_AGENT,
    Role.ELECTION_ADMIN,
    Role.SYSTEM_ADMIN,
)
# Roles that may read every submission, comparison, anomaly and audit trail.
EVIDENCE_STAFF_ROLES: tuple[Role, ...] = (
    Role.REVIEWER,
    Role.AUDITOR,
    Role.ELECTION_ADMIN,
    Role.SYSTEM_ADMIN,
)
# Roles that may approve or reject. Auditors are read-only.
EVIDENCE_REVIEWER_ROLES: tuple[Role, ...] = (Role.REVIEWER, Role.ELECTION_ADMIN)


class EvidenceStatus(StrEnum):
    """VoteTrace workflow status. Not an INEC declaration status."""

    RECEIVED = "received"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    ARITHMETIC_VALIDATED = "arithmetic_validated"
    CROSS_CHECKED = "cross_checked"
    FLAGGED_FOR_REVIEW = "flagged_for_review"
    UNDER_HUMAN_REVIEW = "under_human_review"
    REVIEWED = "reviewed"
    VERIFIED = "verified"
    REJECTED = "rejected"


class PollingUnitResultStatus(StrEnum):
    """Aggregation state of one polling unit for one election. Derived, never client-set.

    not_reporting: no submission that is still in play (none, or all rejected).
    pending: submissions exist but none has passed validation yet.
    reported: accepted submissions agree; not yet verified by human review.
    conflict: accepted submissions disagree; excluded from party totals.
    verified: an agreed result passed the required human approvals.
    """

    NOT_REPORTING = "not_reporting"
    PENDING = "pending"
    REPORTED = "reported"
    CONFLICT = "conflict"
    VERIFIED = "verified"


class ResultStream(StrEnum):
    REPORTED = "reported"
    VERIFIED = "verified"


class EvidenceImageKind(StrEnum):
    ORIGINAL = "original"
    PROCESSED = "processed"


class ExtractionStatus(StrEnum):
    COMPLETED = "completed"
    # No OCR engine was available; every field needs manual transcription.
    OCR_UNAVAILABLE = "ocr_unavailable"
    FAILED = "failed"


class FieldOrigin(StrEnum):
    OCR = "ocr"
    HUMAN = "human"


class AlertCategory(StrEnum):
    OCR_UNCERTAINTY = "ocr_uncertainty"
    SUBMISSION_DISCREPANCY = "submission_discrepancy"
    DUPLICATE_EVIDENCE = "duplicate_evidence"
    STATISTICAL = "statistical"


class AlertSeverity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReviewDecision(StrEnum):
    STARTED = "started"
    APPROVED = "approved"
    REJECTED = "rejected"
    CORRECTION_REQUESTED = "correction_requested"


class ResultSource(StrEnum):
    EXTRACTED = "extracted"
    OFFICIAL = "official"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    VERIFIED = "verified"
    DISCREPANCY = "discrepancy"
    REJECTED = "rejected"


class PollingUnitStatus(StrEnum):
    """Mirrors frontend/src/features/polling-units/status.ts."""

    ACTIVE = "active"
    RELOCATION_REPORTED = "relocation_reported"
    OFFICIALLY_RELOCATED = "officially_relocated"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    PENDING_VERIFICATION = "pending_verification"


class NoticeVerificationStatus(StrEnum):
    """Status of an official notice. Only OFFICIALLY_CONFIRMED may drive an official status."""

    OFFICIALLY_CONFIRMED = "officially_confirmed"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    WITHDRAWN = "withdrawn"


class UpdateCategory(StrEnum):
    POLLING_UNIT_RELOCATION = "polling_unit_relocation"
    ELECTION_SCHEDULE = "election_schedule"
    VOTING_DELAY = "voting_delay"
    OFFICIAL_ANNOUNCEMENT = "official_announcement"
    SECURITY_NOTICE = "security_notice"
    GENERAL_INFORMATION = "general_information"


class UpdateVerificationStatus(StrEnum):
    OFFICIALLY_CONFIRMED = "officially_confirmed"
    INDEPENDENTLY_VERIFIED = "independently_verified"
    REPORTED_UNVERIFIED = "reported_unverified"


class IncidentCategory(StrEnum):
    """Mirrors frontend/src/features/incidents/meta.ts."""

    VIOLENCE = "violence"
    INTIMIDATION = "intimidation"
    VOTE_BUYING = "vote_buying"
    DELAYED_OFFICIALS = "delayed_officials"
    POLLING_UNIT_RELOCATION = "polling_unit_relocation"
    VOTING_DISRUPTION = "voting_disruption"
    ACCESSIBILITY = "accessibility"
    MISINFORMATION = "misinformation"
    OTHER = "other"


class IncidentStatus(StrEnum):
    """Review state of an incident report. Changed only by authorised reviewers."""

    RECEIVED = "received"
    SCREENING = "screening"
    UNDER_REVIEW = "under_review"
    CORROBORATION_REQUIRED = "corroboration_required"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    INCONCLUSIVE = "inconclusive"
    REJECTED = "rejected"
    RESOLVED = "resolved"


class IncidentSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Roles that may read incident reports in the console. Auditors are read-only.
INCIDENT_STAFF_ROLES: tuple[Role, ...] = (
    Role.REVIEWER,
    Role.AUDITOR,
    Role.ELECTION_ADMIN,
    Role.SYSTEM_ADMIN,
)
# Roles that may change an incident's review status.
INCIDENT_REVIEWER_ROLES: tuple[Role, ...] = (Role.REVIEWER, Role.ELECTION_ADMIN)
