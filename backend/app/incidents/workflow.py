"""Incident review states and the transitions reviewers may make."""

from typing import Literal

from app.db.enums import IncidentStatus as I

TRANSITIONS: dict[I, tuple[I, ...]] = {
    I.RECEIVED: (I.SCREENING, I.UNDER_REVIEW, I.REJECTED),
    I.SCREENING: (I.UNDER_REVIEW, I.CORROBORATION_REQUIRED, I.UNVERIFIED, I.REJECTED),
    I.UNDER_REVIEW: (
        I.CORROBORATION_REQUIRED,
        I.VERIFIED,
        I.UNVERIFIED,
        I.INCONCLUSIVE,
        I.REJECTED,
    ),
    I.CORROBORATION_REQUIRED: (I.UNDER_REVIEW, I.VERIFIED, I.UNVERIFIED, I.INCONCLUSIVE),
    I.VERIFIED: (I.RESOLVED,),
    I.UNVERIFIED: (I.UNDER_REVIEW, I.RESOLVED),
    I.INCONCLUSIVE: (I.UNDER_REVIEW, I.RESOLVED),
    I.REJECTED: (I.SCREENING,),
    I.RESOLVED: (),
}

AWAITING_REVIEW = (I.RECEIVED, I.SCREENING)
UNDER_INVESTIGATION = (I.UNDER_REVIEW, I.CORROBORATION_REQUIRED)
OPEN = AWAITING_REVIEW + UNDER_INVESTIGATION
# A decision on these needs at least one reference to supporting material.
NEEDS_EVIDENCE = (I.VERIFIED,)

Band = Literal[
    "reported", "under_review", "corroborated", "verified", "inconclusive", "not_substantiated"
]

BAND_LABEL: dict[str, str] = {
    "reported": "Reported, awaiting review",
    "under_review": "Under review",
    "corroborated": "Under review, with independent similar reports",
    "verified": "Verified by VoteTrace reviewers",
    "inconclusive": "Reviewed, inconclusive",
    "not_substantiated": "Reviewed, not substantiated",
}


def band(status: I, corroborating: int, resolution_basis: I | None = None) -> Band:
    """The public-facing distinction between reported, under review, corroborated,
    verified and inconclusive. Corroboration means independent similar reports exist,
    not that the allegation is established."""
    if status == I.RESOLVED and resolution_basis is not None:
        status = resolution_basis
    if status in AWAITING_REVIEW:
        return "reported"
    if status in UNDER_INVESTIGATION:
        return "corroborated" if corroborating > 0 else "under_review"
    if status == I.VERIFIED:
        return "verified"
    if status == I.INCONCLUSIVE:
        return "inconclusive"
    return "not_substantiated"


def can_publish(status: I, resolution_basis: I | None) -> bool:
    """Only reviewer-verified incidents may be shown to the public, and only through a
    summary the reviewer writes."""
    return status == I.VERIFIED or (status == I.RESOLVED and resolution_basis == I.VERIFIED)
