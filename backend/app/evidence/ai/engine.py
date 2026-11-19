import uuid
from dataclasses import dataclass, field
from typing import Any

from app.db.enums import AlertCategory, AlertSeverity

HEADLINE = "Anomaly detected. Human review required."
RECOMMENDATION = (
    "A trained reviewer should examine the original result-sheet image and the flagged "
    "fields. This alert is not a finding of fraud or wrongdoing."
)


@dataclass(frozen=True)
class Alert:
    category: AlertCategory
    severity: AlertSeverity
    summary: str
    fields: list[str]
    # what / why / contributing_fields / metrics — shown to reviewers verbatim.
    explanation: dict[str, Any]
    model_name: str
    model_version: str
    recommendation: str = RECOMMENDATION
    headline: str = HEADLINE
    is_demo: bool = False


@dataclass
class AnalysisResult:
    run_id: uuid.UUID
    alerts: list[Alert] = field(default_factory=list)
    statistical: dict[str, Any] = field(default_factory=dict)


def analyze(
    *,
    fields: list[dict[str, Any]],
    comparison: dict[str, Any] | None,
    target_values: dict[str, int | str | None],
    reference_values: list[dict[str, int | str | None]],
    party_keys: list[str],
    min_samples: int,
    threshold: float,
) -> AnalysisResult:
    from app.evidence.ai.discrepancy import discrepancy_alerts
    from app.evidence.ai.statistical import statistical_analysis
    from app.evidence.ai.uncertainty import uncertainty_alerts

    result = AnalysisResult(run_id=uuid.uuid4())
    result.alerts += uncertainty_alerts(fields, threshold)
    if comparison is not None:
        result.alerts += discrepancy_alerts(comparison)
    statistical, alert = statistical_analysis(
        target_values, reference_values, party_keys, min_samples
    )
    result.statistical = statistical
    if alert is not None:
        result.alerts.append(alert)
    return result
