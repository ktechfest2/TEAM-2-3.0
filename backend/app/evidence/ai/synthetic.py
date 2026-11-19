"""DEMO / SYNTHETIC polling-unit results for exercising the statistical anomaly check.

Every record here is fictional. None is an INEC result or real reviewed evidence. The
figures are generated from a fixed seed so the dataset, and therefore every anomaly
score, is the same on every run.

Most records follow an ordinary pattern. A few are deliberately unusual (very high
accreditation, a very high rejected-vote share, one party taking almost every vote).
All of them are arithmetically consistent, so they pass the deterministic checks: they
are statistical outliers, not arithmetic failures or conflicting submissions.

The `kind` of each record is kept for the report and the tests only. It is never given
to the model, which is unsupervised and sees nothing but the figures."""

import random
from dataclasses import dataclass
from typing import Any

from app.evidence.ai.statistical import FEATURES, features, statistical_analysis

SYNTHETIC_LABEL = "DEMO / SYNTHETIC data. Fictional figures, not an INEC result."
DEFAULT_SEED = 20261119
ORDINARY_REFERENCE = 36
ORDINARY_TARGETS = 4
INJECTED_KINDS = (
    "high_accreditation",
    "high_rejected_share",
    "dominant_party",
    "high_accreditation_and_dominant_party",
)

Values = dict[str, int | str | None]


@dataclass(frozen=True)
class SyntheticRecord:
    name: str
    # "ordinary" or one of INJECTED_KINDS. Never shown to the model.
    kind: str
    # Reviewed records form the reference the model learns from; the others are scored
    # against it, as new submissions would be.
    reviewed: bool
    values: Values

    @property
    def injected(self) -> bool:
        return self.kind != "ordinary"


def _split(valid: int, leading_share: float, parties: list[str], rng: random.Random) -> Values:
    leader = rng.randrange(len(parties))
    lead_votes = round(valid * leading_share)
    rest = valid - lead_votes
    others = [p for i, p in enumerate(parties) if i != leader]
    weights = [rng.uniform(0.6, 1.4) for _ in others]
    votes = [int(rest * w / sum(weights)) for w in weights]
    votes[0] += rest - sum(votes)
    split: Values = {parties[leader]: lead_votes}
    split.update(zip(others, votes, strict=True))
    return {p: split[p] for p in parties}


def _record(
    rng: random.Random,
    parties: list[str],
    *,
    accreditation: tuple[float, float] = (0.30, 0.46),
    rejected: tuple[float, float] = (0.012, 0.038),
    leading: tuple[float, float] = (0.36, 0.52),
) -> Values:
    registered = rng.randint(450, 1300)
    accredited = round(registered * rng.uniform(*accreditation))
    cast = accredited - rng.randint(0, 4)
    rejected_votes = round(cast * rng.uniform(*rejected))
    valid = cast - rejected_votes
    return {
        "registered_voters": registered,
        "accredited_voters": accredited,
        "rejected_votes": rejected_votes,
        "total_valid_votes": valid,
        "total_votes_cast": cast,
        **_split(valid, rng.uniform(*leading), parties, rng),
    }


_INJECTED = {
    "high_accreditation": {"accreditation": (0.95, 0.98)},
    "high_rejected_share": {"rejected": (0.22, 0.26)},
    "dominant_party": {"leading": (0.94, 0.96)},
    "high_accreditation_and_dominant_party": {
        "accreditation": (0.90, 0.93),
        "leading": (0.89, 0.92),
    },
}


def synthetic_dataset(party_keys: list[str], seed: int = DEFAULT_SEED) -> list[SyntheticRecord]:
    """36 reviewed ordinary records, then 4 ordinary and 4 injected unreviewed records."""
    if len(party_keys) < 2:
        raise ValueError("at least two parties are needed")
    rng = random.Random(seed)
    records = [
        SyntheticRecord(f"SYNTHETIC-REF-{i + 1:02d}", "ordinary", True, _record(rng, party_keys))
        for i in range(ORDINARY_REFERENCE)
    ]
    records += [
        SyntheticRecord(f"SYNTHETIC-NEW-{i + 1:02d}", "ordinary", False, _record(rng, party_keys))
        for i in range(ORDINARY_TARGETS)
    ]
    records += [
        SyntheticRecord(
            f"SYNTHETIC-ODD-{i + 1:02d}", kind, False, _record(rng, party_keys, **_INJECTED[kind])
        )
        for i, kind in enumerate(INJECTED_KINDS)
    ]
    return records


def evaluate(
    records: list[SyntheticRecord], party_keys: list[str], min_samples: int
) -> list[dict[str, Any]]:
    """Score every record with the production statistical check.

    Unreviewed records are scored against all reviewed ones. Each reviewed record is
    scored against the other reviewed records (leave one out), mirroring how the service
    excludes a record's own polling unit from its reference."""
    reviewed = [r for r in records if r.reviewed]
    results = []
    for record in records:
        reference = [r.values for r in reviewed if r is not record]
        summary, alert = statistical_analysis(
            record.values, reference, party_keys, min_samples, is_demo=True
        )
        results.append(
            {
                "name": record.name,
                "kind": record.kind,
                "reviewed": record.reviewed,
                "features": {
                    k: None if v is None else round(v, 4)
                    for k, v in features(record.values, party_keys).items()
                },
                "summary": summary,
                "alert": alert,
            }
        )
    return results


def describe_features() -> dict[str, str]:
    return dict(FEATURES)
