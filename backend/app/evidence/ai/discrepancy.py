"""Turn a comparison between submissions into a review alert."""

from typing import Any

from app.db.enums import AlertCategory, AlertSeverity
from app.evidence.ai.engine import Alert

MODEL_NAME = "submission-discrepancy-rules"
MODEL_VERSION = "1"


def _severity(relative: float) -> AlertSeverity:
    if relative >= 0.2:
        return AlertSeverity.HIGH
    if relative >= 0.05:
        return AlertSeverity.MEDIUM
    return AlertSeverity.LOW


def discrepancy_alerts(comparison: dict[str, Any]) -> list[Alert]:
    alerts: list[Alert] = []
    conflicts = [f for f in comparison["fields"] if f["status"] == "conflict"]
    if conflicts:
        largest = max(float(f.get("relative_difference", "1")) for f in conflicts)
        alerts.append(
            Alert(
                category=AlertCategory.SUBMISSION_DISCREPANCY,
                severity=_severity(largest),
                summary=f"{len(conflicts)} figure(s) differ between "
                f"{comparison['submission_count']} submissions for this polling unit.",
                fields=[f["field_key"] for f in conflicts],
                explanation={
                    "what": "Conflicting figures across independent submissions",
                    "why": "Submissions for the same election and polling unit report different "
                    "values. Possible causes include OCR errors, photos of different sheets, or "
                    "altered figures; the cause is not determined automatically.",
                    "contributing_fields": [
                        {
                            "field_key": f["field_key"],
                            "values": f["values"],
                            "most_common_value": f.get("most_common_value"),
                            "differing_submissions": f.get("differing_submissions", []),
                            "max_difference": f.get("max_difference"),
                            "relative_difference": f.get("relative_difference"),
                        }
                        for f in conflicts
                    ],
                    "metrics": {"largest_relative_difference": f"{largest:.4f}"},
                },
                model_name=MODEL_NAME,
                model_version=MODEL_VERSION,
            )
        )
    duplicates = [d for d in comparison["duplicates"] if d["type"] != "same_submitter"]
    if duplicates:
        identical = any(d["type"] == "identical_file" for d in duplicates)
        alerts.append(
            Alert(
                category=AlertCategory.DUPLICATE_EVIDENCE,
                severity=AlertSeverity.MEDIUM if identical else AlertSeverity.LOW,
                summary="Some submissions appear to use the same photograph, so they are not "
                "independent evidence.",
                fields=[],
                explanation={
                    "what": "Possible duplicate evidence",
                    "why": "Identical file fingerprints or visually near-identical photos were "
                    "found. Agreement between such submissions does not confirm the result.",
                    "contributing_fields": duplicates,
                    "metrics": {"pairs": len(duplicates)},
                },
                model_name=MODEL_NAME,
                model_version=MODEL_VERSION,
            )
        )
    return alerts
