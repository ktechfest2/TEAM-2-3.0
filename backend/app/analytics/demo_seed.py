"""Sample data. Not an official election result.

Populate the fictional demo election with synthetic result-sheet submissions so the
dashboard can be explored:

    python -m app.analytics.demo_seed

Every submission goes through the real evidence workflow (upload and hashing, manual
transcription, deterministic validation, comparison, and two-reviewer approval), so the
statuses and totals the dashboard shows are produced by the same rules as live data.
Images are generated and stamped "DEMONSTRATION"; figures are random but internally
consistent. Nothing here is INEC data. Refuses to run in production or against an
election that is not marked as a demo."""

import io
import random
import uuid
from collections import Counter
from dataclasses import dataclass

from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal
from app.db.enums import Role
from app.db.models import EvidenceSubmission
from app.directory.repository import DirectoryRepository, get_directory
from app.evidence import service
from app.evidence.ocr import NullProvider
from app.evidence.storage import EvidenceStorage
from app.evidence.templates import party_key
from app.schemas.elections import Election
from app.schemas.polling_units import PollingUnitSummary

DEMO_LABEL = "Sample data. Not an official election result."
_NAMESPACE = uuid.UUID("0b3f7a52-9d5e-4c1e-8f43-5d7e1f0c2a61")


def demo_principal(name: str, *roles: Role) -> Principal:
    return Principal(user_id=uuid.uuid5(_NAMESPACE, name), email=None, roles=list(roles))


OBSERVER = demo_principal("demo-observer", Role.OBSERVER)
AGENT = demo_principal("demo-party-agent", Role.PARTY_AGENT)
SECOND_OBSERVER = demo_principal("demo-observer-2", Role.OBSERVER)
REVIEWERS = (
    demo_principal("demo-reviewer-1", Role.REVIEWER),
    demo_principal("demo-reviewer-2", Role.REVIEWER),
)


def demo_sheet_image(seed: int, lines: list[str]) -> bytes:
    """A generated page stamped as demonstration data. Different seeds differ visibly, so
    separate submissions are not mistaken for copies of one photo."""
    rng = random.Random(seed)
    image = Image.new("RGB", (900, 1200), (250, 250, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 880, 70), fill=(180, 30, 30))
    draw.text((40, 38), "DEMONSTRATION - NOT A REAL RESULT SHEET", fill="white")
    for row, line in enumerate(lines):
        draw.text((60, 110 + row * 40), line, fill="black")
    for _ in range(30):
        x, y = rng.randint(0, 840), rng.randint(500, 1140)
        w, h = rng.randint(10, 60), rng.randint(10, 60)
        shade = rng.randint(0, 200)
        draw.rectangle((x, y, x + w, y + h), outline=(shade, shade, shade), width=2)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=85)
    return buffer.getvalue()


def demo_values(
    unit: PollingUnitSummary, election: Election, rng: random.Random
) -> dict[str, int | str | None]:
    """Random but arithmetically consistent figures for one fictional polling unit."""
    registered = rng.randint(350, 1400)
    accredited = int(registered * rng.uniform(0.25, 0.65))
    rejected = int(accredited * rng.uniform(0.005, 0.04))
    cast = max(rejected, accredited - rng.randint(0, 5))
    valid = cast - rejected
    # Party strength varies by state so state comparisons are not identical.
    bias = sum(ord(c) for c in unit.state.name) % len(election.parties)
    weights = [
        rng.uniform(0.6, 1.4) * (2.2 if i == bias else 1.0) / (1 + i * 0.35)
        for i in range(len(election.parties))
    ]
    total_weight = sum(weights)
    votes = [int(valid * w / total_weight) for w in weights]
    votes[weights.index(max(weights))] += valid - sum(votes)
    values: dict[str, int | str | None] = {
        "polling_unit_code": unit.code,
        "election_label": election.election_label,
        "registered_voters": registered,
        "accredited_voters": accredited,
        "rejected_votes": rejected,
        "total_valid_votes": valid,
        "total_votes_cast": cast,
    }
    for party, count in zip(election.parties, votes, strict=True):
        values[party_key(party.code)] = count
    return values


def _sheet_lines(values: dict[str, int | str | None]) -> list[str]:
    return [f"{key.replace('_', ' ').upper()}: {value}" for key, value in values.items()]


@dataclass
class DemoPipeline:
    """Drives the real evidence service for generated demonstration submissions."""

    db: Session
    storage: EvidenceStorage
    settings: Settings
    directory: DirectoryRepository
    election: Election

    def submit(
        self,
        unit_id: uuid.UUID,
        submitter: Principal,
        values: dict[str, int | str | None],
        seed: int,
    ) -> EvidenceSubmission:
        unit = self.directory.get_polling_unit(unit_id)
        assert unit is not None
        upload = service.Upload(
            data=demo_sheet_image(seed, _sheet_lines(values)),
            filename=f"demo-{unit.code}-{seed}.jpg",
            content_type="image/jpeg",
            idempotency_key=uuid.uuid5(_NAMESPACE, f"{self.election.id}/{unit.id}/{seed}"),
            captured_at=None,
            client_sha256=None,
            client_info={"capture_source": "demo_generator"},
        )
        submission, _ = service.ingest(
            self.db, self.storage, self.settings, submitter, self.election, unit, upload
        )
        return submission

    def transcribe(
        self, submission: EvidenceSubmission, submitter: Principal, values: dict
    ) -> None:
        service.process(
            self.db,
            self.storage,
            NullProvider(),
            self.settings,
            submission,
            self.election,
            submitter,
        )
        service.correct(
            self.db,
            submission,
            self.election,
            submitter,
            [service.Correction(key, value, None) for key, value in values.items()],
        )

    def validate(self, submission: EvidenceSubmission, actor: Principal) -> None:
        unit = self.directory.get_polling_unit(submission.polling_unit_id)
        assert unit is not None
        service.validate(self.db, submission, self.election, unit, actor, self.settings)

    def review(
        self, submission: EvidenceSubmission, reviewer: Principal, action: str, notes: str | None
    ) -> None:
        service.review(self.db, submission, reviewer, action, notes, self.settings)

    def verify(self, submission: EvidenceSubmission) -> None:
        notes = "Demonstration review: values checked against the generated sheet."
        self.review(submission, REVIEWERS[0], "start", None)
        for reviewer in REVIEWERS[: self.settings.verification_required_approvals]:
            self.review(submission, reviewer, "approve", notes)

    def accepted(
        self, unit_id: uuid.UUID, submitter: Principal, values: dict, seed: int
    ) -> EvidenceSubmission:
        submission = self.submit(unit_id, submitter, values, seed)
        self.transcribe(submission, submitter, values)
        self.validate(submission, submitter)
        return submission


SCENARIOS = (
    "verified",
    "reported",
    "not_reporting",
    "verified_two_sources",
    "conflict",
    "verified",
    "pending",
    "flagged_arithmetic",
    "under_review",
    "not_reporting",
    "verified",
    "rejected",
    "reported",
)


def seed_unit(pipeline: DemoPipeline, unit: PollingUnitSummary, scenario: str, index: int) -> None:
    rng = random.Random(f"{pipeline.election.id}/{unit.code}")
    values = demo_values(unit, pipeline.election, rng)
    seed = index * 10
    if scenario == "pending":
        pipeline.submit(unit.id, OBSERVER, values, seed)
        return
    if scenario == "flagged_arithmetic":
        wrong = dict(values)
        wrong["total_valid_votes"] = int(values["total_valid_votes"] or 0) + 7  # type: ignore[arg-type]
        pipeline.accepted(unit.id, OBSERVER, wrong, seed)
        return
    first = pipeline.accepted(unit.id, OBSERVER, values, seed)
    if scenario == "reported":
        return
    if scenario == "under_review":
        pipeline.review(first, REVIEWERS[0], "start", None)
        return
    if scenario == "rejected":
        pipeline.review(first, REVIEWERS[0], "start", None)
        pipeline.review(first, REVIEWERS[0], "reject", "Demonstration: image does not match.")
        return
    if scenario == "conflict":
        other = dict(values)
        first_party = party_key(pipeline.election.parties[0].code)
        second_party = party_key(pipeline.election.parties[1].code)
        shift = min(15, int(other[second_party] or 0))  # type: ignore[arg-type]
        other[first_party] = int(other[first_party] or 0) + shift  # type: ignore[arg-type]
        other[second_party] = int(other[second_party] or 0) - shift  # type: ignore[arg-type]
        pipeline.accepted(unit.id, AGENT, other, seed + 1)
        return
    if scenario == "verified_two_sources":
        pipeline.accepted(unit.id, AGENT, values, seed + 1)
    pipeline.verify(first)


def seed(
    db: Session,
    storage: EvidenceStorage,
    settings: Settings,
    directory: DirectoryRepository,
    election: Election,
) -> Counter[str]:
    if settings.is_production:
        raise SystemExit("Refusing to create demonstration data in production.")
    if not election.is_demo or directory.source.kind != "demo":
        raise SystemExit("Demonstration data may only be added to a demo election.")
    pipeline = DemoPipeline(db, storage, settings, directory, election)
    already = set(
        db.scalars(
            select(EvidenceSubmission.polling_unit_id)
            .where(EvidenceSubmission.election_id == election.id)
            .distinct()
        )
    )
    created: Counter[str] = Counter()
    for index, unit in enumerate(directory.list_all_polling_units()):
        if unit.id in already:
            continue
        scenario = SCENARIOS[index % len(SCENARIOS)]
        if scenario == "not_reporting":
            continue
        seed_unit(pipeline, unit, scenario, index)
        created[scenario] += 1
    return created


def main() -> None:
    from app.evidence.db import evidence_session_factory
    from app.evidence.storage import get_storage

    settings = get_settings()
    directory = get_directory()
    election = next(e for e in directory.list_elections() if e.election_label == "PRESIDENTIAL")
    with evidence_session_factory()() as db:
        created = seed(db, get_storage(), settings, directory, election)
    print(DEMO_LABEL)
    print(f"Election: {election.name}")
    for scenario, count in sorted(created.items()):
        print(f"  {scenario}: {count} polling units")
    print("Units not listed above are left without submissions (not reporting).")


if __name__ == "__main__":
    main()
