"""Score a result against other reviewed results from the same election.

Uses an Isolation Forest on four ratios. It is not a fraud classifier and is
not trained on made-up labels. It stays quiet until enough reviewed records
exist to compare against."""

from typing import Any

import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest

from app.db.enums import AlertCategory, AlertSeverity
from app.evidence.ai.engine import Alert

MODEL_NAME = "isolation-forest"
FEATURE_VERSION = "features-v1"
MODEL_VERSION = f"sklearn-{sklearn.__version__}/{FEATURE_VERSION}"
RANDOM_STATE = 20261118
ROBUST_Z_THRESHOLD = 3.0

FEATURES = {
    "turnout_of_accredited": "Votes cast ÷ accredited voters",
    "rejected_share": "Rejected votes ÷ votes cast",
    "leading_party_share": "Leading party votes ÷ valid votes",
    "accredited_of_registered": "Accredited voters ÷ voters on the register",
}


def _ratio(numerator: object, denominator: object) -> float | None:
    if not isinstance(numerator, int) or not isinstance(denominator, int) or denominator <= 0:
        return None
    return numerator / denominator


def features(values: dict[str, int | str | None], party_keys: list[str]) -> dict[str, float | None]:
    party_votes = [values.get(k) for k in party_keys]
    leading = max((v for v in party_votes if isinstance(v, int)), default=None)
    return {
        "turnout_of_accredited": _ratio(
            values.get("total_votes_cast"), values.get("accredited_voters")
        ),
        "rejected_share": _ratio(values.get("rejected_votes"), values.get("total_votes_cast")),
        "leading_party_share": _ratio(leading, values.get("total_valid_votes")),
        "accredited_of_registered": _ratio(
            values.get("accredited_voters"), values.get("registered_voters")
        ),
    }


def statistical_analysis(
    target: dict[str, int | str | None],
    reference: list[dict[str, int | str | None]],
    party_keys: list[str],
    min_samples: int,
    *,
    is_demo: bool = False,
) -> tuple[dict[str, Any], Alert | None]:
    target_features = features(target, party_keys)
    rows = [features(r, party_keys) for r in reference]
    # Use only variables available for the target and for every reference record.
    usable = [
        name
        for name in FEATURES
        if target_features[name] is not None and all(row[name] is not None for row in rows)
    ]
    base = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "variables": usable,
        "reference_records": len(rows),
        "min_samples": min_samples,
        "is_demo": is_demo,
    }
    if len(rows) < min_samples or len(usable) < 2:
        return {
            **base,
            "status": "insufficient_data",
            "detail": f"Statistical analysis needs at least {min_samples} human-reviewed records "
            f"with comparable figures for this election; {len(rows)} available.",
        }, None

    matrix = np.array([[row[name] for name in usable] for row in rows], dtype=float)
    point = np.array([[target_features[name] for name in usable]], dtype=float)
    model = IsolationForest(n_estimators=200, contamination="auto", random_state=RANDOM_STATE)
    model.fit(matrix)
    score = float(model.decision_function(point)[0])
    is_outlier = bool(model.predict(point)[0] == -1)

    median = np.median(matrix, axis=0)
    mad = np.median(np.abs(matrix - median), axis=0) * 1.4826
    contributions = []
    for index, name in enumerate(usable):
        spread = mad[index] if mad[index] > 1e-9 else 1e-9
        z = (point[0, index] - median[index]) / spread
        contributions.append(
            {
                "variable": name,
                "description": FEATURES[name],
                "value": f"{point[0, index]:.4f}",
                "reference_median": f"{median[index]:.4f}",
                "robust_z": f"{z:.2f}",
                "unusual": bool(abs(z) >= ROBUST_Z_THRESHOLD),
            }
        )
    contributions.sort(key=lambda c: -abs(float(c["robust_z"])))
    summary = {
        **base,
        "status": "analysed",
        "anomaly_score": f"{score:.4f}",
        "is_outlier": is_outlier,
    }
    if not is_outlier:
        return summary, None

    unusual = [c for c in contributions if c["unusual"]] or contributions[:1]
    return summary, Alert(
        category=AlertCategory.STATISTICAL,
        severity=AlertSeverity.MEDIUM if score < -0.1 else AlertSeverity.LOW,
        summary="This record's figures are statistically unusual compared with "
        f"{len(rows)} human-reviewed records for the same election.",
        fields=[c["variable"] for c in unusual],
        explanation={
            "what": "Unusual voting pattern",
            "why": "Isolation Forest isolated this record faster than typical records. The "
            "variables listed differ most from the reference median. Unusual is not the same "
            "as wrong: genuine local circumstances can produce unusual figures.",
            "contributing_fields": contributions,
            "metrics": {"anomaly_score": f"{score:.4f}", "reference_records": len(rows)},
        },
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        is_demo=is_demo,
    )
