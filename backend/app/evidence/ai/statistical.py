"""Score a result against other reviewed results from the same election.

Uses an Isolation Forest on four ratios. It is not a fraud classifier and is
not trained on made-up labels. It stays quiet until enough reviewed records
exist to compare against.

Valid votes ÷ votes cast is not a separate variable: for any record that passes the
arithmetic checks it equals 1 − rejected share, and repeating it would double that
variable's weight in the forest."""

from typing import Any

import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest

from app.db.enums import AlertCategory, AlertSeverity
from app.evidence.ai.engine import Alert

MODEL_NAME = "isolation-forest"
FEATURE_VERSION = "features-v1"
DECISION_VERSION = "empirical-p-v1"
MODEL_VERSION = f"sklearn-{sklearn.__version__}/{FEATURE_VERSION}/{DECISION_VERSION}"
RANDOM_STATE = 20261118
# A record is flagged when at most this share of the records scored with it are as
# isolated. The smallest possible p-value is 1 / (reference + 1), so at least 19
# reference records are needed before anything can be flagged.
ALPHA = 0.05
ROBUST_Z_THRESHOLD = 3.0
DEMO_PREFIX = "DEMO / SYNTHETIC data, not a real election result. "

FEATURES = {
    "turnout_of_accredited": "Votes cast ÷ accredited voters",
    "rejected_share": "Rejected votes ÷ votes cast",
    "leading_party_share": "Leading party votes ÷ valid votes",
    "accredited_of_registered": "Accredited voters ÷ voters on the register",
}


def _count(value: object) -> int | None:
    """A usable vote count: a non-negative int. Booleans, text and negatives are ignored
    rather than coerced, so a malformed figure can never shape the reference model."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _ratio(numerator: object, denominator: object) -> float | None:
    top, bottom = _count(numerator), _count(denominator)
    if top is None or bottom is None or bottom == 0:
        return None
    return top / bottom


def features(values: dict[str, int | str | None], party_keys: list[str]) -> dict[str, float | None]:
    party_votes = [_count(values.get(k)) for k in party_keys]
    leading = max((v for v in party_votes if v is not None), default=None)
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
    if min_samples < 2:
        raise ValueError("min_samples must be at least 2")
    target_features = features(target, party_keys)
    all_rows = [features(r, party_keys) for r in reference]
    # Variables this record has, kept only if enough reference records have them too.
    # Reference records missing any kept variable are left out, not imputed.
    usable = [
        name
        for name in FEATURES
        if target_features[name] is not None
        and sum(row[name] is not None for row in all_rows) >= min_samples
    ]
    rows = [row for row in all_rows if all(row[name] is not None for name in usable)]
    base = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "variables": usable,
        "reference_records": len(rows),
        "excluded_reference_records": len(all_rows) - len(rows),
        "min_samples": min_samples,
        "is_demo": is_demo,
    }
    record_variables = sum(value is not None for value in target_features.values())
    if record_variables < 2:
        return {
            **base,
            "status": "insufficient_data",
            "detail": "Statistical analysis needs at least two usable figures on this record "
            "(whole numbers of zero or more with a non-zero base); "
            f"{record_variables} available.",
        }, None
    if len(rows) < min_samples or len(usable) < 2:
        return {
            **base,
            "status": "insufficient_data",
            "detail": f"Statistical analysis needs at least {min_samples} human-reviewed records "
            f"with comparable figures for this election; {len(rows)} available.",
        }, None

    matrix = np.array([[row[name] for name in usable] for row in rows], dtype=float)
    point = np.array([[target_features[name] for name in usable]], dtype=float)
    # The record under test is fitted together with the reference. Isolation Forest only
    # splits inside the range of the data it was fitted on, so a record fitted out of
    # sample would never be separated from the most extreme reference record, however far
    # beyond it the record lies.
    together = np.vstack([matrix, point])
    model = IsolationForest(n_estimators=200, contamination="auto", random_state=RANDOM_STATE)
    model.fit(together)
    scores = model.score_samples(together)
    score = float(model.decision_function(point)[0])
    # Empirical p-value: the share of all scored records at least as isolated as this
    # one. Every record is treated alike, so for an ordinary record it is roughly uniform
    # and the false-alert rate is about ALPHA. The fixed "auto" cut-off is not used: with
    # a few dozen records it flags around half of ordinary records.
    p_value = float(np.mean(scores <= scores[-1]))
    is_outlier = p_value <= ALPHA

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
        "empirical_p_value": f"{p_value:.4f}",
        "alpha": ALPHA,
        "is_outlier": is_outlier,
        "contributing_fields": contributions,
    }
    if not is_outlier:
        return summary, None

    unusual = [c for c in contributions if c["unusual"]]
    prefix = DEMO_PREFIX if is_demo else ""
    return summary, Alert(
        category=AlertCategory.STATISTICAL,
        # Medium only when a ratio is also far from typical, not merely the most isolated.
        severity=AlertSeverity.MEDIUM if unusual else AlertSeverity.LOW,
        summary=f"{prefix}This record's figures are statistically unusual compared with "
        f"{len(rows)} human-reviewed records for the same election.",
        fields=[c["variable"] for c in (unusual or contributions[:1])],
        explanation={
            "what": "Unusual voting pattern",
            "why": "Isolation Forest isolated this record faster than "
            f"{100 * (1 - p_value):.0f}% of the {len(rows)} human-reviewed records it was "
            "compared with. The variables listed differ most from the reference median. "
            "Unusual is not the same as wrong: genuine local circumstances can produce "
            "unusual figures.",
            "contributing_fields": contributions,
            "metrics": {
                "anomaly_score": f"{score:.4f}",
                "empirical_p_value": f"{p_value:.4f}",
                "alpha": ALPHA,
                "reference_records": len(rows),
            },
        },
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        is_demo=is_demo,
    )
