"""Deterministic incident triage.

Every output here is advisory and explained. Nothing in this module changes the
reporter's category or words, decides whether an allegation is true, or names anyone.
Reviewers see the rule that fired and can correct the category and severity."""

import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.db.enums import IncidentCategory as C
from app.db.enums import IncidentSeverity as S

METHOD = "verivote-incident-rules-v1"
CLASSIFICATION_NOTE = (
    "Keyword suggestion only. The reporter's category is kept until a reviewer changes it. "
    "A report is an allegation until reviewers verify it."
)

# Lower-case words or phrases. Matched on word boundaries against the normalised text.
KEYWORDS: dict[C, tuple[str, ...]] = {
    C.VIOLENCE: (
        "gun",
        "guns",
        "gunshot",
        "gunshots",
        "shooting",
        "shot",
        "machete",
        "knife",
        "attack",
        "attacked",
        "beat",
        "beaten",
        "beating",
        "injured",
        "wounded",
        "killed",
        "fight",
        "fighting",
        "thug",
        "thugs",
        "stabbed",
        "bomb",
        "explosion",
        "set ablaze",
        "burnt",
        "violence",
        "violent",
        "kill",
        "weapon",
        "weapons",
    ),
    C.INTIMIDATION: (
        "intimidate",
        "intimidated",
        "intimidation",
        "harass",
        "harassed",
        "harassment",
        "threaten",
        "threatened",
        "threats",
        "scared",
        "fear",
        "chased",
        "turned away",
        "forced",
        "coerced",
        "warned voters",
        "prevented from voting",
    ),
    C.VOTE_BUYING: (
        "cash",
        "money",
        "naira",
        "bribe",
        "bribed",
        "bribery",
        "buying votes",
        "vote buying",
        "paid",
        "envelope",
        "envelopes",
        "transfer",
        "gift",
        "gifts",
        "rice",
        "inducement",
    ),
    C.DELAYED_OFFICIALS: (
        "late",
        "delay",
        "delayed",
        "not arrived",
        "yet to arrive",
        "no officials",
        "officials absent",
        "still waiting",
        "hours late",
        "did not open",
        "not opened",
    ),
    C.POLLING_UNIT_RELOCATION: (
        "relocated",
        "relocation",
        "moved",
        "new location",
        "changed location",
        "shifted",
        "different location",
        "moved to",
    ),
    C.VOTING_DISRUPTION: (
        "disrupt",
        "disrupted",
        "disruption",
        "snatched",
        "snatching",
        "ballot box",
        "stopped",
        "suspended",
        "bvas",
        "card reader",
        "malfunction",
        "not working",
        "materials",
        "shortage",
        "chaos",
        "stampede",
        "tampered",
    ),
    C.ACCESSIBILITY: (
        "wheelchair",
        "disability",
        "disabled",
        "blind",
        "deaf",
        "elderly",
        "ramp",
        "stairs",
        "pregnant",
        "braille",
        "accessible",
        "inaccessible",
        "pwd",
        "pwds",
    ),
    C.MISINFORMATION: (
        "fake news",
        "rumour",
        "rumor",
        "misinformation",
        "disinformation",
        "whatsapp",
        "broadcast",
        "viral",
        "hoax",
        "false claim",
        "false message",
        "propaganda",
    ),
}

BASE_SEVERITY: dict[C, S] = {
    C.VIOLENCE: S.HIGH,
    C.INTIMIDATION: S.MEDIUM,
    C.VOTE_BUYING: S.MEDIUM,
    C.DELAYED_OFFICIALS: S.LOW,
    C.POLLING_UNIT_RELOCATION: S.LOW,
    C.VOTING_DISRUPTION: S.MEDIUM,
    C.ACCESSIBILITY: S.LOW,
    C.MISINFORMATION: S.LOW,
    C.OTHER: S.LOW,
}
CRITICAL_TERMS = (
    "killed",
    "dead",
    "death",
    "gunshot",
    "gunshots",
    "shooting",
    "bomb",
    "explosion",
    "kidnapped",
    "abducted",
    "stabbed",
    "set ablaze",
)
ESCALATING_TERMS = (
    "injured",
    "wounded",
    "bleeding",
    "hospital",
    "beaten",
    "weapon",
    "weapons",
    "gun",
    "machete",
    "armed",
    "knife",
)
URGENCY_TERMS = ("ongoing", "right now", "happening now", "still happening", "currently")
SCALE_TERMS = ("crowd", "many voters", "hundreds", "dozens", "everyone")
ORDER = [S.LOW, S.MEDIUM, S.HIGH, S.CRITICAL]

# Nigerian mobile numbers, international numbers and e-mail addresses.
_PHONE = re.compile(r"(?<!\d)(?:\+?234|0)[789][01]\d{8}(?!\d)|\+\d[\d\s-]{8,14}\d")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have he her his i in is it its of on or our she "
    "that the their them they this to was we were with who you your there here been very".split()
)


@dataclass(frozen=True)
class Classification:
    suggested: C | None
    matches: dict[str, list[str]]


@dataclass(frozen=True)
class SeverityResult:
    severity: S
    reasons: list[str]


@dataclass
class TriageResult:
    classification: Classification
    severity: SeverityResult
    missing: list[dict[str, str]]
    redacted: bool
    similar: list[dict[str, Any]] = field(default_factory=list)

    def as_json(self, reported: C) -> dict[str, Any]:
        suggested = self.classification.suggested
        return {
            "method": METHOD,
            "classification": {
                "suggested_category": suggested.value if suggested else None,
                "agrees_with_reporter": suggested is None or suggested == reported,
                "matched_keywords": self.classification.matches,
                "note": CLASSIFICATION_NOTE,
            },
            "severity": {
                "level": self.severity.severity.value,
                "reasons": self.severity.reasons,
            },
            "missing_information": self.missing,
            "personal_data_redacted": self.redacted,
            "similar_reports": self.similar,
            "corroborating_reports": len(self.similar),
        }


def clean_text(value: str) -> tuple[str, bool]:
    """Strip control characters, collapse whitespace and mask phone numbers and e-mails.
    Returns the cleaned text and whether anything personal was masked."""
    text = _CONTROL.sub("", unicodedata.normalize("NFC", value))
    text = re.sub(r"[ \t]+", " ", text).strip()
    masked = _PHONE.sub("[number removed]", text)
    masked = _EMAIL.sub("[e-mail removed]", masked)
    return masked, masked != text


def _normalised(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip() + " "


def _contains(normalised: str, term: str) -> bool:
    return f" {term} " in normalised


def classify(description: str) -> Classification:
    text = _normalised(description)
    matches: dict[str, list[str]] = {}
    for category, terms in KEYWORDS.items():
        found = sorted({t for t in terms if _contains(text, t)})
        if found:
            matches[category.value] = found
    if not matches:
        return Classification(None, {})
    ranked = sorted(matches.items(), key=lambda item: len(item[1]), reverse=True)
    if len(ranked) > 1 and len(ranked[0][1]) == len(ranked[1][1]):
        return Classification(None, matches)
    return Classification(C(ranked[0][0]), matches)


def assess_severity(category: C, description: str) -> SeverityResult:
    text = _normalised(description)
    level = BASE_SEVERITY[category]
    reasons = [f"Base level for this category: {level.value}."]
    critical = sorted(t for t in CRITICAL_TERMS if _contains(text, t))
    if critical:
        reasons.append(f"Mentions possible loss of life or grave harm: {', '.join(critical)}.")
        return SeverityResult(S.CRITICAL, reasons)

    def bump(current: S) -> S:
        return ORDER[min(ORDER.index(current) + 1, len(ORDER) - 2)]

    escalating = sorted(t for t in ESCALATING_TERMS if _contains(text, t))
    if escalating:
        level = bump(level)
        reasons.append(f"Mentions injury or weapons: {', '.join(escalating)}.")
    urgent = sorted(t for t in URGENCY_TERMS if _contains(text, t))
    if urgent:
        level = bump(level)
        reasons.append(f"Described as ongoing: {', '.join(urgent)}.")
    scale = sorted(t for t in SCALE_TERMS if _contains(text, t))
    if scale and level == S.LOW:
        level = S.MEDIUM
        reasons.append(f"Describes many people affected: {', '.join(scale)}.")
    reasons.append("Severity sets review order only. It is not a finding.")
    return SeverityResult(level, reasons)


def missing_information(
    *,
    description: str,
    ward_id: uuid.UUID | None,
    polling_unit_id: uuid.UUID | None,
    time_is_approximate: bool,
    has_coordinates: bool,
    has_attachment: bool,
) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    if polling_unit_id is None:
        missing.append({"field": "polling_unit", "message": "No polling unit given."})
    if ward_id is None:
        missing.append({"field": "ward", "message": "No ward given."})
    if len(description) < 80:
        missing.append(
            {"field": "description", "message": "Short description. Details may be missing."}
        )
    if time_is_approximate:
        missing.append({"field": "time", "message": "The time is approximate."})
    if not has_coordinates:
        missing.append({"field": "coordinates", "message": "No map location shared."})
    if not has_attachment:
        missing.append({"field": "image", "message": "No supporting image."})
    return missing


def tokens(text: str) -> frozenset[str]:
    return frozenset(
        word for word in _normalised(text).split() if len(word) > 2 and word not in _STOPWORDS
    )


def similarity(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def fingerprint(
    *,
    election_id: uuid.UUID,
    category: C,
    lga_id: uuid.UUID,
    ward_id: uuid.UUID | None,
    polling_unit_id: uuid.UUID | None,
    description: str,
) -> str:
    """Identifies an exact resubmission of the same report text at the same place."""
    parts = [
        str(election_id),
        category.value,
        str(lga_id),
        str(ward_id or "-"),
        str(polling_unit_id or "-"),
        " ".join(_normalised(description).split()),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def area_key(election_id: uuid.UUID, lga_id: uuid.UUID, ward_id: uuid.UUID | None) -> str:
    """Geographic group: election, LGA and ward (or the whole LGA when no ward is known)."""
    return f"{election_id.hex}:{lga_id.hex}:{ward_id.hex if ward_id else '-'}"
