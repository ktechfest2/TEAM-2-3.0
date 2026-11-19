"""Seed, score and clean up the DEMO / SYNTHETIC statistical-anomaly dataset.

    python -m app.evidence.ai.anomaly_demo report           # score the dataset, no database
    python -m app.evidence.ai.anomaly_demo seed [--dir D]   # fill a dedicated demo store
    python -m app.evidence.ai.anomaly_demo cleanup [--dir D]

Safety rules:
  * It writes only to its own SQLite file and evidence folder (default var/anomaly-demo),
    never to DATABASE_URL, the preview store or any database it did not create. A marker
    file identifies that folder; a folder without the marker is never written to or
    deleted.
  * Records go into a fictional election of the demo directory only, stamped with
    capture_source "synthetic_anomaly_demo". The statistical check never compares them
    with genuine records.
  * History tables are append-only, so cleanup deletes the whole dedicated folder rather
    than rows, and refuses if the folder holds any submission the generator did not make.
  * Every record goes through the real workflow: upload and hashing, transcription,
    validation, comparison and analysis. Ordinary reference records are approved by two
    demo reviewers. Unusual records are left for a human: an anomaly is a review alert,
    never a rejection."""

import argparse
import json
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.analytics.demo_seed import AGENT, OBSERVER, DemoPipeline, demo_principal
from app.core.config import Settings, get_settings
from app.db.enums import AlertCategory, Role
from app.db.models import AnomalyAlert, EvidenceSubmission
from app.directory.repository import DemoDirectoryRepository, DirectoryRepository
from app.evidence import service
from app.evidence.ai.synthetic import SYNTHETIC_LABEL, SyntheticRecord, evaluate, synthetic_dataset
from app.evidence.storage import EvidenceStorage, LocalStorage
from app.evidence.templates import party_key
from app.schemas.elections import Election

DEMO_ELECTION_LABEL = "HOUSE OF ASSEMBLY"
MARKER = ".synthetic-anomaly-demo"
DEFAULT_DIR = "var/anomaly-demo"
DATABASE_FILE = "anomaly-demo.sqlite3"
REVIEW_NOTES = "DEMO / SYNTHETIC review: figures checked against the generated sheet."
SYNTHETIC_REVIEWERS = (
    demo_principal("synthetic-reviewer-1", Role.REVIEWER),
    demo_principal("synthetic-reviewer-2", Role.REVIEWER),
)


class DemoRefused(SystemExit):
    pass


@dataclass
class SeedReport:
    election: str
    reviewed: int = 0
    awaiting_review: list[dict] = field(default_factory=list)
    skipped: int = 0


def demo_election(directory: DirectoryRepository) -> Election:
    return next(e for e in directory.list_elections() if e.election_label == DEMO_ELECTION_LABEL)


def party_keys(election: Election) -> list[str]:
    return [party_key(p.code) for p in election.parties]


class _SyntheticPipeline(DemoPipeline):
    def submit(self, unit_id, submitter, values, seed):  # type: ignore[no-untyped-def]
        unit = self.directory.get_polling_unit(unit_id)
        assert unit is not None
        upload = service.Upload(
            data=_sheet(values, seed),
            filename=f"synthetic-{unit.code}.jpg",
            content_type="image/jpeg",
            idempotency_key=uuid.uuid5(
                uuid.NAMESPACE_URL, f"synthetic-anomaly/{self.election.id}/{unit.id}"
            ),
            captured_at=None,
            client_sha256=None,
            client_info={"capture_source": service.SYNTHETIC_SOURCE},
        )
        submission, _ = service.ingest(
            self.db, self.storage, self.settings, submitter, self.election, unit, upload
        )
        return submission


def _sheet(values: dict, seed: int) -> bytes:
    from app.analytics.demo_seed import demo_sheet_image

    lines = ["DEMO / SYNTHETIC - FICTIONAL FIGURES - NOT AN INEC RESULT"]
    lines += [f"{k.replace('_', ' ').upper()}: {v}" for k, v in values.items()]
    return demo_sheet_image(seed, lines)


def assert_seedable(
    db: Session, settings: Settings, directory: DirectoryRepository, election: Election
) -> None:
    if settings.is_production:
        raise DemoRefused("Refusing to create synthetic data in production.")
    if directory.source.kind != "demo" or not election.is_demo:
        raise DemoRefused("Synthetic data may only be added to an election of the demo directory.")
    foreign = [
        s
        for s in db.scalars(
            select(EvidenceSubmission).where(EvidenceSubmission.election_id == election.id)
        )
        if not service.is_synthetic(s)
    ]
    if foreign:
        raise DemoRefused(
            f"{election.name} already holds {len(foreign)} submission(s) that are not synthetic. "
            "Nothing was changed."
        )


def seed_synthetic(
    db: Session,
    storage: EvidenceStorage,
    settings: Settings,
    directory: DirectoryRepository,
    records: list[SyntheticRecord] | None = None,
) -> SeedReport:
    """Seed the dataset through the real evidence workflow. Re-running adds nothing."""
    election = demo_election(directory)
    assert_seedable(db, settings, directory, election)
    keys = party_keys(election)
    records = records if records is not None else synthetic_dataset(keys)
    units = sorted(directory.list_all_polling_units(), key=lambda u: u.code)
    if len(units) < len(records):
        raise DemoRefused(
            f"The demo directory has {len(units)} polling units; need {len(records)}."
        )
    pipeline = _SyntheticPipeline(db, storage, settings, directory, election)
    done = set(
        db.scalars(
            select(EvidenceSubmission.polling_unit_id).where(
                EvidenceSubmission.election_id == election.id
            )
        )
    )
    report = SeedReport(election=election.name)
    # Reviewed reference records first, so later records have something to compare with.
    ordered = sorted(enumerate(records), key=lambda pair: not pair[1].reviewed)
    for index, record in ordered:
        unit = units[index]
        if unit.id in done:
            report.skipped += 1
            continue
        values = {
            "polling_unit_code": unit.code,
            "election_label": election.election_label,
            **record.values,
        }
        submitter = OBSERVER if index % 2 == 0 else AGENT
        submission = pipeline.accepted(unit.id, submitter, values, seed=1000 + index)
        if record.reviewed:
            service.review(db, submission, SYNTHETIC_REVIEWERS[0], "start", None, settings)
            for reviewer in SYNTHETIC_REVIEWERS[: settings.verification_required_approvals]:
                service.review(db, submission, reviewer, "approve", REVIEW_NOTES, settings)
            report.reviewed += 1
        else:
            report.awaiting_review.append(_scored(db, record, unit.code, submission))
    return report


def _scored(db: Session, record: SyntheticRecord, code: str, submission) -> dict:  # type: ignore[no-untyped-def]
    db.refresh(submission)
    validation = service.latest_validation(db, submission.id)
    assert validation is not None
    statistical = validation.report.get("statistical_analysis", {})
    run = validation.report.get("analysis_run_id")
    categories = sorted(
        AlertCategory(a.category).value
        for a in db.scalars(select(AnomalyAlert).where(AnomalyAlert.submission_id == submission.id))
        if str(a.analysis_run_id) == run
    )
    return {
        "name": record.name,
        "polling_unit": code,
        "submission_id": str(submission.id),
        "status": submission.workflow_status,
        "arithmetic_passed": validation.passed,
        "statistical": statistical.get("status"),
        "anomaly_score": statistical.get("anomaly_score"),
        "empirical_p_value": statistical.get("empirical_p_value"),
        "alerts": categories,
    }


def _resolve(directory: str) -> Path:
    base = (Path.cwd() / "var").resolve()
    path = (Path.cwd() / directory).resolve()
    if base not in path.parents:
        raise DemoRefused(f"The demo folder must be inside {base}.")
    return path


def _open(path: Path) -> tuple[sessionmaker[Session], LocalStorage]:
    from app.evidence.db import create_dev_engine

    engine = create_dev_engine(str(path / DATABASE_FILE))
    return (
        sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
        LocalStorage(str(path / "evidence"), get_settings().evidence_bucket),
    )


def seed_command(directory: str) -> SeedReport:
    path = _resolve(directory)
    if path.exists() and any(path.iterdir()) and not (path / MARKER).exists():
        raise DemoRefused(f"{path} exists and was not created by this tool. Nothing was changed.")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    (path / MARKER).write_text(SYNTHETIC_LABEL + "\n")
    factory, storage = _open(path)
    with factory() as db:
        return seed_synthetic(db, storage, get_settings(), DemoDirectoryRepository())


def cleanup_command(directory: str) -> bool:
    path = _resolve(directory)
    if not path.exists():
        return False
    if not (path / MARKER).exists():
        raise DemoRefused(f"{path} was not created by this tool. Nothing was deleted.")
    database = path / DATABASE_FILE
    if database.exists():
        factory, _ = _open(path)
        with factory() as db:
            foreign = [
                s for s in db.scalars(select(EvidenceSubmission)) if not service.is_synthetic(s)
            ]
        factory.kw["bind"].dispose()
        if foreign:
            raise DemoRefused(
                f"{path} holds {len(foreign)} submission(s) the generator did not make. "
                "Nothing was deleted; remove the folder by hand if you are sure."
            )
    shutil.rmtree(path)
    return True


def report_command() -> list[dict]:
    election = demo_election(DemoDirectoryRepository())
    keys = party_keys(election)
    results = evaluate(synthetic_dataset(keys), keys, get_settings().anomaly_min_samples)
    return [
        {
            "name": r["name"],
            "kind": r["kind"],
            "reviewed": r["reviewed"],
            "features": r["features"],
            "status": r["summary"]["status"],
            "anomaly_score": r["summary"].get("anomaly_score"),
            "empirical_p_value": r["summary"].get("empirical_p_value"),
            "flagged": r["alert"] is not None,
            "severity": r["alert"].severity.value if r["alert"] else None,
            "unusual_fields": r["alert"].fields if r["alert"] else [],
            "why": r["alert"].explanation["why"] if r["alert"] else None,
            "contributing_fields": r["summary"].get("contributing_fields", []),
        }
        for r in results
    ]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="DEMO / SYNTHETIC statistical anomaly data")
    parser.add_argument("command", choices=["report", "seed", "cleanup"])
    parser.add_argument("--dir", default=DEFAULT_DIR, help="dedicated folder under var/")
    parser.add_argument("--json", action="store_true", help="report as JSON")
    args = parser.parse_args(argv)
    print(SYNTHETIC_LABEL, file=sys.stderr)
    if args.command == "report":
        rows = report_command()
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
            return
        for row in rows:
            top = row["contributing_fields"][0] if row["contributing_fields"] else {}
            print(
                f"{row['name']:17} {row['kind']:38} score={row['anomaly_score']} "
                f"p={row['empirical_p_value']} flagged={row['flagged']} "
                f"top={top.get('variable')} z={top.get('robust_z')}"
            )
        print(f"{sum(r['flagged'] for r in rows)} of {len(rows)} records flagged")
    elif args.command == "seed":
        result = seed_command(args.dir)
        print(
            f"{result.election}: {result.reviewed} reviewed synthetic records, "
            f"{len(result.awaiting_review)} awaiting human review, {result.skipped} skipped"
        )
        for row in result.awaiting_review:
            print(
                f"  {row['name']} {row['polling_unit']}: {row['status']}, "
                f"score {row['anomaly_score']}, p {row['empirical_p_value']}, "
                f"alerts {row['alerts'] or 'none'}"
            )
    else:
        removed = cleanup_command(args.dir)
        print("Removed the synthetic demo folder." if removed else "Nothing to remove.")


if __name__ == "__main__":
    main()
