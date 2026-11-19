"""Compare submissions for the same election and polling unit.

Agreement between submissions is not proof of independence: two uploads of the
same photo, or several uploads by one person, will agree trivially. Disagreement
is not proof of wrongdoing: it may be an OCR error, a correction, or a photo of a
different sheet. The report recommends human review; it never assigns blame."""

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations
from typing import Any

from app.evidence.hashing import canonical_timestamp, hamming_distance

NEAR_DUPLICATE_DISTANCE = 6


@dataclass(frozen=True)
class SubmissionSnapshot:
    id: uuid.UUID
    submitted_by: uuid.UUID
    received_at: datetime
    original_sha256: str
    perceptual_hash: str | None
    values: dict[str, int | str | None]


def _utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes (stored as UTC); new objects in a session are aware.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _relative_difference(values: list[int]) -> float:
    high, low = max(values), min(values)
    return (high - low) / max(high, 1)


def compare_submissions(
    target: SubmissionSnapshot,
    others: list[SubmissionSnapshot],
    compared_fields: list[str],
    compared_at: datetime,
) -> dict[str, Any]:
    snapshots = sorted([target, *others], key=lambda s: (_utc(s.received_at), str(s.id)))
    ids = [str(s.id) for s in snapshots]

    duplicates: list[dict[str, Any]] = []
    for a, b in combinations(snapshots, 2):
        pair = [str(a.id), str(b.id)]
        if a.original_sha256 == b.original_sha256:
            duplicates.append(
                {
                    "type": "identical_file",
                    "submission_ids": pair,
                    "detail": "Both submissions contain the same image file (identical SHA-256).",
                }
            )
        elif a.perceptual_hash and b.perceptual_hash:
            distance = hamming_distance(a.perceptual_hash, b.perceptual_hash)
            if distance <= NEAR_DUPLICATE_DISTANCE:
                duplicates.append(
                    {
                        "type": "near_duplicate_image",
                        "submission_ids": pair,
                        "hamming_distance": distance,
                        "detail": "The photos are visually near-identical; one may be a re-upload "
                        "or edited copy of the other.",
                    }
                )
        if a.submitted_by == b.submitted_by:
            duplicates.append(
                {
                    "type": "same_submitter",
                    "submission_ids": pair,
                    "detail": "Both submissions come from the same account, so they are not "
                    "independent confirmations.",
                }
            )

    dependent_pairs = {frozenset(d["submission_ids"]) for d in duplicates}

    fields: list[dict[str, Any]] = []
    for key in compared_fields:
        by_submission = {str(s.id): s.values.get(key) for s in snapshots}
        present = {sid: v for sid, v in by_submission.items() if v is not None}
        distinct = sorted({str(v) for v in present.values()})
        entry: dict[str, Any] = {"field_key": key, "values": by_submission}
        if len(present) < 2:
            entry["status"] = "incomplete"
        elif len(distinct) == 1:
            entry["status"] = "match"
        else:
            entry["status"] = "conflict"
            counts = Counter(str(v) for v in present.values())
            top, top_count = counts.most_common(1)[0]
            if top_count > 1 and list(counts.values()).count(top_count) == 1:
                entry["most_common_value"] = top
                entry["differing_submissions"] = sorted(
                    sid for sid, v in present.items() if str(v) != top
                )
            numbers = [v for v in present.values() if isinstance(v, int)]
            if len(numbers) == len(present):
                entry["max_difference"] = max(numbers) - min(numbers)
                entry["relative_difference"] = f"{_relative_difference(numbers):.4f}"
        fields.append(entry)

    matching = [f["field_key"] for f in fields if f["status"] == "match"]
    conflicting = [f["field_key"] for f in fields if f["status"] == "conflict"]

    independent_agreement = [
        f["field_key"]
        for f in fields
        if f["status"] == "match"
        and any(
            frozenset([a, b]) not in dependent_pairs
            for a, b in combinations([sid for sid, v in f["values"].items() if v is not None], 2)
        )
    ]

    if len(snapshots) < 2:
        recommendation = {
            "code": "no_comparison",
            "text": "No other submission exists for this polling unit yet. A single submission "
            "cannot be cross-checked.",
        }
    elif conflicting:
        recommendation = {
            "code": "review_conflicts",
            "text": "Submissions disagree on one or more figures. A reviewer should compare the "
            "original images. A difference does not by itself indicate wrongdoing by any party.",
        }
    elif duplicates:
        recommendation = {
            "code": "review_dependence",
            "text": "Figures agree, but some submissions may not be independent (same file, "
            "near-identical photo or same submitter). Treat the agreement with caution.",
        }
    else:
        recommendation = {
            "code": "consistent",
            "text": "Submissions agree on every compared figure. Human review is still required "
            "before verification.",
        }

    return {
        "submission_ids": ids,
        "submission_count": len(snapshots),
        "compared_fields": compared_fields,
        "fields": fields,
        "matching_fields": matching,
        "conflicting_fields": conflicting,
        "independently_matching_fields": independent_agreement,
        "duplicates": duplicates,
        "compared_at": canonical_timestamp(compared_at),
        "recommendation": recommendation,
    }
