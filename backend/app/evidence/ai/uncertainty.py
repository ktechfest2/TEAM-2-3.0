"""Rank OCR fields that a reviewer should confirm by hand."""

from typing import Any

from app.db.enums import AlertCategory, AlertSeverity
from app.evidence.ai.engine import Alert

MODEL_NAME = "ocr-uncertainty-rules"
MODEL_VERSION = "1"
_TOTALS = {"total_valid_votes", "total_votes_cast", "accredited_voters", "rejected_votes"}


def _priority(field: dict[str, Any], threshold: float) -> int:
    score = 0
    confidence = field.get("confidence")
    if field.get("value") is None:
        score += 3
    elif confidence is not None and confidence < threshold / 2:
        score += 3
    elif confidence is not None and confidence < threshold:
        score += 1
    if field.get("ambiguous_characters"):
        score += 2
    if field["field_key"] in _TOTALS or field["field_key"].startswith("party:"):
        score += 1
    return score


def uncertainty_alerts(fields: list[dict[str, Any]], threshold: float) -> list[Alert]:
    """`fields` are effective fields still awaiting human confirmation."""
    pending = [f for f in fields if f.get("requires_review") and f.get("origin") == "ocr"]
    if not pending:
        return []
    ranked = sorted(pending, key=lambda f: (-_priority(f, threshold), f["field_key"]))
    top = _priority(ranked[0], threshold)
    severity = (
        AlertSeverity.HIGH if top >= 4 else AlertSeverity.MEDIUM if top >= 2 else AlertSeverity.LOW
    )
    return [
        Alert(
            category=AlertCategory.OCR_UNCERTAINTY,
            severity=severity,
            summary=f"{len(ranked)} extracted field(s) could not be read with confidence and "
            "must be confirmed by a person.",
            fields=[f["field_key"] for f in ranked],
            explanation={
                "what": "Uncertain OCR readings",
                "why": "Confidence below the configured threshold, characters that resemble "
                "digits (for example O and 0), or a field that was not found on the sheet.",
                "contributing_fields": [
                    {
                        "field_key": f["field_key"],
                        "value": f.get("value"),
                        "confidence": None
                        if f.get("confidence") is None
                        else f"{f['confidence']:.2f}",
                        "reasons": f.get("review_reasons", []),
                        "ambiguous_characters": f.get("ambiguous_characters", []),
                        "priority": _priority(f, threshold),
                    }
                    for f in ranked
                ],
                "metrics": {"threshold": f"{threshold:.2f}"},
            },
            model_name=MODEL_NAME,
            model_version=MODEL_VERSION,
        )
    ]
