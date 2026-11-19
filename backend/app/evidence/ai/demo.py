"""Controlled demonstration of the statistical analysis.

DEMONSTRATION ONLY. The reference records are synthetic values generated here,
not election data, and the result is not a validated finding. Run with:

    python -m app.evidence.ai.demo
"""

import json
import random

from app.evidence.ai.statistical import statistical_analysis

DEMO_LABEL = "DEMONSTRATION: synthetic values, not election data"
PARTY_KEYS = ["party:PA", "party:PB", "party:PC"]


def synthetic_record(rng: random.Random) -> dict[str, int | str | None]:
    registered = rng.randint(600, 1200)
    accredited = int(registered * rng.uniform(0.3, 0.45))
    rejected = int(accredited * rng.uniform(0.01, 0.04))
    valid = accredited - rejected - rng.randint(0, 5)
    shares = [rng.uniform(0.3, 0.45), rng.uniform(0.25, 0.4)]
    pa, pb = int(valid * shares[0]), int(valid * shares[1])
    return {
        "registered_voters": registered,
        "accredited_voters": accredited,
        "rejected_votes": rejected,
        "total_valid_votes": valid,
        "total_votes_cast": valid + rejected,
        "party:PA": pa,
        "party:PB": pb,
        "party:PC": valid - pa - pb,
    }


def demo_reference(count: int = 60, seed: int = 7) -> list[dict[str, int | str | None]]:
    rng = random.Random(seed)
    return [synthetic_record(rng) for _ in range(count)]


def demo_unusual_record() -> dict[str, int | str | None]:
    """Synthetic record with near-total turnout of the register and one dominant party."""
    return {
        "registered_voters": 800,
        "accredited_voters": 790,
        "rejected_votes": 2,
        "total_valid_votes": 786,
        "total_votes_cast": 788,
        "party:PA": 780,
        "party:PB": 4,
        "party:PC": 2,
    }


def run_demo() -> dict:
    summary, alert = statistical_analysis(
        demo_unusual_record(), demo_reference(), PARTY_KEYS, min_samples=30, is_demo=True
    )
    return {
        "label": DEMO_LABEL,
        "summary": summary,
        "alert": None
        if alert is None
        else {
            "headline": alert.headline,
            "summary": alert.summary,
            "fields": alert.fields,
            "explanation": alert.explanation,
            "is_demo": alert.is_demo,
        },
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2, ensure_ascii=False))
