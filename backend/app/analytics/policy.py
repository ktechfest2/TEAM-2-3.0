"""Aggregation policy: how the submissions for one polling unit become at most one
reported result and at most one verified result.

1. Rejected submissions are ignored entirely (they are still listed in the evidence API).
2. A submission is *accepted* when its workflow has passed deterministic validation and
   that validation passed: arithmetic_validated, cross_checked, flagged_for_review,
   under_human_review, reviewed or verified, with a passing latest validation.
   Received, processing and extracted submissions, and those whose validation failed,
   are pending: they show that evidence arrived, but contribute no figures.
3. Accepted submissions are grouped by result fingerprint (SHA-256 of the canonical
   values). One group means the submissions agree; that single set of values is the
   unit's reported result, counted once no matter how many people sent it.
4. More than one group is a conflict. All submissions are kept and listed, the unit
   counts as reporting, and its figures are excluded from both reported and verified
   totals until reviewers reject the wrong submission(s).
5. The verified result exists only when there is no conflict and at least one agreeing
   submission reached VERIFIED through the required human approvals.

Independent submissions are agreeing submissions from different accounts whose images
are neither identical nor near-duplicates of an earlier one. They are reported for
transparency; they never multiply a unit's votes."""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from app.db.enums import EvidenceStatus as S
from app.db.enums import PollingUnitResultStatus as R
from app.evidence.comparison import NEAR_DUPLICATE_DISTANCE
from app.evidence.hashing import hamming_distance

ACCEPTED_STATUSES = frozenset(
    {
        S.ARITHMETIC_VALIDATED,
        S.CROSS_CHECKED,
        S.FLAGGED_FOR_REVIEW,
        S.UNDER_HUMAN_REVIEW,
        S.REVIEWED,
        S.VERIFIED,
    }
)
TOTAL_METRICS = (
    "registered_voters",
    "accredited_voters",
    "total_valid_votes",
    "rejected_votes",
    "total_votes_cast",
)
PARTY_PREFIX = "party:"


@dataclass(frozen=True)
class SubmissionState:
    id: uuid.UUID
    submitted_by: uuid.UUID
    status: S
    received_at: datetime
    status_changed_at: datetime
    original_sha256: str
    perceptual_hash: str | None
    validation_passed: bool | None = None
    validated_at: datetime | None = None
    result_hash: str | None = None
    values: dict[str, int | str | None] = field(default_factory=dict)
    has_alerts: bool = False

    @property
    def accepted(self) -> bool:
        return (
            self.status in ACCEPTED_STATUSES
            and self.validation_passed is True
            and self.result_hash is not None
        )


@dataclass(frozen=True)
class PolicyOutcome:
    status: R
    submission_count: int
    accepted_count: int
    independent_count: int
    rejected_count: int
    distinct_results: int
    has_flagged: bool
    has_anomaly: bool
    reported_result_hash: str | None
    verified_result_hash: str | None
    reported_metrics: dict[str, int]
    verified_metrics: dict[str, int]
    source_submission_ids: list[str]
    contributing_submission_ids: list[str]
    first_reported_at: datetime | None
    verified_at: datetime | None
    last_submission_at: datetime | None


def result_metrics(values: dict[str, int | str | None]) -> dict[str, int]:
    """The numeric figures that are summed up the hierarchy."""
    return {
        key: value
        for key, value in values.items()
        if (key in TOTAL_METRICS or key.startswith(PARTY_PREFIX))
        and isinstance(value, int)
        and not isinstance(value, bool)
    }


def count_independent(submissions: list[SubmissionState]) -> int:
    """Distinct accounts with distinct photos. Duplicate or near-duplicate images of the
    same sheet, and repeat uploads from one account, do not add independence."""
    seen_accounts: set[uuid.UUID] = set()
    seen_files: set[str] = set()
    seen_hashes: list[str] = []
    independent = 0
    for item in sorted(submissions, key=lambda s: (s.received_at, str(s.id))):
        near = item.perceptual_hash is not None and any(
            hamming_distance(item.perceptual_hash, other) <= NEAR_DUPLICATE_DISTANCE
            for other in seen_hashes
        )
        if item.submitted_by not in seen_accounts and item.original_sha256 not in seen_files:
            if not near:
                independent += 1
        seen_accounts.add(item.submitted_by)
        seen_files.add(item.original_sha256)
        if item.perceptual_hash:
            seen_hashes.append(item.perceptual_hash)
    return independent


def decide(submissions: list[SubmissionState]) -> PolicyOutcome:
    live = [s for s in submissions if s.status != S.REJECTED]
    rejected = len(submissions) - len(live)
    accepted = [s for s in live if s.accepted]
    groups: dict[str, list[SubmissionState]] = defaultdict(list)
    for item in accepted:
        groups[item.result_hash or ""].append(item)

    reported_hash: str | None = None
    verified_hash: str | None = None
    reported_metrics: dict[str, int] = {}
    verified_metrics: dict[str, int] = {}
    contributing: list[SubmissionState] = []
    verified_at: datetime | None = None

    if not live:
        status = R.NOT_REPORTING
    elif not accepted:
        status = R.PENDING
    elif len(groups) > 1:
        status = R.CONFLICT
    else:
        [(reported_hash, contributing)] = groups.items()
        reported_metrics = result_metrics(contributing[0].values)
        verified = [s for s in contributing if s.status == S.VERIFIED]
        if verified:
            status = R.VERIFIED
            verified_hash = reported_hash
            verified_metrics = dict(reported_metrics)
            verified_at = min(s.status_changed_at for s in verified)
        else:
            status = R.REPORTED

    accepted_times = [s.validated_at for s in accepted if s.validated_at is not None]
    return PolicyOutcome(
        status=status,
        submission_count=len(live),
        accepted_count=len(accepted),
        independent_count=count_independent(contributing) if contributing else 0,
        rejected_count=rejected,
        distinct_results=len(groups),
        has_flagged=any(s.status == S.FLAGGED_FOR_REVIEW for s in live),
        has_anomaly=any(s.has_alerts for s in live),
        reported_result_hash=reported_hash,
        verified_result_hash=verified_hash,
        reported_metrics=reported_metrics,
        verified_metrics=verified_metrics,
        source_submission_ids=sorted(str(s.id) for s in live),
        contributing_submission_ids=sorted(str(s.id) for s in contributing),
        first_reported_at=min(accepted_times) if accepted_times else None,
        verified_at=verified_at,
        last_submission_at=max((s.received_at for s in live), default=None),
    )
