"""Statistical anomaly detection on the DEMO / SYNTHETIC dataset.

Every record here is fictional. The model under test is the production Isolation Forest;
nothing is mocked and no anomaly label is ever given to it."""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.demo_seed import AGENT, DemoPipeline
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import Principal
from app.db.enums import AlertCategory, AlertSeverity, EvidenceStatus, Role
from app.db.models import AnomalyAlert, EvidenceSubmission
from app.directory.repository import DemoDirectoryRepository
from app.evidence import service
from app.evidence.ai import anomaly_demo
from app.evidence.ai.statistical import ALPHA, RANDOM_STATE, features, statistical_analysis
from app.evidence.ai.synthetic import (
    INJECTED_KINDS,
    ORDINARY_REFERENCE,
    evaluate,
    synthetic_dataset,
)

DIRECTORY = DemoDirectoryRepository()
ELECTION = anomaly_demo.demo_election(DIRECTORY)
PARTIES = anomaly_demo.party_keys(ELECTION)
DATASET = synthetic_dataset(PARTIES)
REFERENCE = [r.values for r in DATASET if r.reviewed]
BY_NAME = {r.name: r for r in DATASET}
EXPECTED_DRIVER = {
    "high_accreditation": "accredited_of_registered",
    "high_rejected_share": "rejected_share",
    "dominant_party": "leading_party_share",
    "high_accreditation_and_dominant_party": "accredited_of_registered",
}


@pytest.fixture(scope="module")
def results() -> dict[str, dict]:
    return {r["name"]: r for r in evaluate(DATASET, PARTIES, min_samples=30)}


def ordinary(**overrides):
    values = dict(REFERENCE[0])
    values.update(overrides)
    return values


# Dataset


def test_dataset_is_labelled_sized_and_arithmetically_consistent():
    assert len(DATASET) >= 30 + len(INJECTED_KINDS)
    assert sum(r.reviewed for r in DATASET) == ORDINARY_REFERENCE >= 30
    assert all(r.name.startswith("SYNTHETIC-") for r in DATASET)
    assert {r.kind for r in DATASET if r.injected} == set(INJECTED_KINDS)
    assert not any(r.injected and r.reviewed for r in DATASET)
    for record in DATASET:
        v = record.values
        assert v["total_valid_votes"] == sum(v[p] for p in PARTIES)
        assert v["total_votes_cast"] == v["total_valid_votes"] + v["rejected_votes"]
        assert v["total_votes_cast"] <= v["accredited_voters"] <= v["registered_voters"]


def test_features_are_the_documented_ratios():
    values = {
        "registered_voters": 1000,
        "accredited_voters": 400,
        "total_votes_cast": 380,
        "rejected_votes": 19,
        "total_valid_votes": 361,
        "party:PA": 200,
        "party:PB": 161,
    }
    assert features(values, ["party:PA", "party:PB"]) == {
        "turnout_of_accredited": 380 / 400,
        "rejected_share": 19 / 380,
        "leading_party_share": 200 / 361,
        "accredited_of_registered": 400 / 1000,
    }


# Minimum data


def test_insufficient_reviewed_records_raise_no_alert():
    odd = BY_NAME["SYNTHETIC-ODD-02"].values
    summary, alert = statistical_analysis(odd, REFERENCE[:29], PARTIES, min_samples=30)
    assert summary["status"] == "insufficient_data"
    assert "at least 30 human-reviewed records" in summary["detail"]
    assert alert is None
    summary, alert = statistical_analysis(odd, REFERENCE[:30], PARTIES, min_samples=30)
    assert summary["status"] == "analysed" and alert is not None


def test_small_reference_sets_can_never_reach_significance():
    """With 10 records the smallest p-value is 1/11, above ALPHA, so nothing is flagged."""
    odd = BY_NAME["SYNTHETIC-ODD-04"].values
    summary, alert = statistical_analysis(odd, REFERENCE[:10], PARTIES, min_samples=10)
    assert summary["status"] == "analysed"
    assert float(summary["empirical_p_value"]) == pytest.approx(1 / 11, abs=1e-4)
    assert 1 / 11 > ALPHA
    assert alert is None


def test_minimum_threshold_is_not_lowered():
    assert get_settings().anomaly_min_samples >= 10
    from app.core.config import Settings

    assert Settings.model_fields["anomaly_min_samples"].default == 30


# Ordinary and injected records


def test_ordinary_new_records_are_not_flagged(results):
    new = [r for r in DATASET if r.kind == "ordinary" and not r.reviewed]
    assert new
    for record in new:
        assert results[record.name]["alert"] is None, record.name
        assert float(results[record.name]["summary"]["empirical_p_value"]) > ALPHA


def test_false_alert_rate_on_reviewed_records_is_near_alpha(results):
    flagged = [r for r in DATASET if r.reviewed and results[r.name]["alert"] is not None]
    assert len(flagged) <= 2
    for record in flagged:
        alert = results[record.name]["alert"]
        assert alert.severity == AlertSeverity.LOW  # no ratio is materially unusual


@pytest.mark.parametrize("kind", INJECTED_KINDS)
def test_injected_anomalies_are_flagged_and_explained(results, kind):
    record = next(r for r in DATASET if r.kind == kind)
    result = results[record.name]
    summary, alert = result["summary"], result["alert"]
    assert summary["is_outlier"] is True
    assert float(summary["empirical_p_value"]) <= ALPHA
    assert alert is not None
    assert alert.category == AlertCategory.STATISTICAL
    assert alert.severity == AlertSeverity.MEDIUM
    assert EXPECTED_DRIVER[kind] in alert.fields
    top = alert.explanation["contributing_fields"][0]
    assert top["variable"] == EXPECTED_DRIVER[kind]
    assert top["unusual"] is True and abs(float(top["robust_z"])) >= 3
    assert alert.headline == "Anomaly detected. Human review required."
    assert "not a finding of fraud" in alert.recommendation
    assert alert.is_demo is True and alert.summary.startswith("DEMO / SYNTHETIC")
    assert "fraud" not in alert.summary.lower()


def test_records_far_outside_the_reference_range_are_the_most_isolated(results):
    """Regression: fitted out of sample, these scored like ordinary edge records."""
    ordinary_scores = [
        float(results[r.name]["summary"]["anomaly_score"])
        for r in DATASET
        if r.kind == "ordinary"
    ]
    for record in (r for r in DATASET if r.injected):
        assert float(results[record.name]["summary"]["anomaly_score"]) < min(ordinary_scores)


# Reproducibility


def test_dataset_and_scores_are_reproducible(results):
    assert synthetic_dataset(PARTIES) == DATASET
    assert synthetic_dataset(PARTIES, seed=1) != DATASET
    again = {r["name"]: r for r in evaluate(DATASET, PARTIES, min_samples=30)}
    for name, result in results.items():
        assert again[name]["summary"] == result["summary"]
    assert RANDOM_STATE == 20261118


# Missing values and invalid inputs


def test_missing_target_values_drop_only_the_affected_ratios():
    summary, _ = statistical_analysis(
        ordinary(rejected_votes=None), REFERENCE, PARTIES, min_samples=30
    )
    assert summary["status"] == "analysed"
    assert "rejected_share" not in summary["variables"]
    assert "turnout_of_accredited" in summary["variables"]


def test_incomplete_reference_records_are_excluded_not_imputed():
    reference = [dict(v) for v in REFERENCE]
    for row in reference[:4]:
        row["accredited_voters"] = None
    summary, _ = statistical_analysis(ordinary(), reference, PARTIES, min_samples=30)
    assert summary["status"] == "analysed"
    assert summary["reference_records"] == len(REFERENCE) - 4
    assert summary["excluded_reference_records"] == 4

    for row in reference[:10]:
        row["registered_voters"] = None
        row["rejected_votes"] = None
    summary, alert = statistical_analysis(ordinary(), reference, PARTIES, min_samples=30)
    assert "accredited_of_registered" not in summary["variables"]
    assert summary["reference_records"] >= 30 or summary["status"] == "insufficient_data"
    assert alert is None or summary["reference_records"] >= 30


@pytest.mark.parametrize(
    "bad",
    [
        {"accredited_voters": -5},
        {"accredited_voters": True},
        {"accredited_voters": "400"},
        {"accredited_voters": 3.5},
    ],
)
def test_invalid_figures_are_ignored_rather_than_coerced(bad):
    computed = features(ordinary(**bad), PARTIES)
    assert computed["turnout_of_accredited"] is None
    assert computed["accredited_of_registered"] is None
    assert computed["rejected_share"] is not None


def test_a_zero_count_is_a_value_but_never_a_divisor():
    computed = features(ordinary(accredited_voters=0), PARTIES)
    assert computed["accredited_of_registered"] == 0.0
    assert computed["turnout_of_accredited"] is None


def test_a_record_without_usable_figures_is_not_scored():
    junk = {key: "n/a" for key in REFERENCE[0]}
    summary, alert = statistical_analysis(junk, REFERENCE, PARTIES, min_samples=30)
    assert summary["status"] == "insufficient_data"
    assert "usable figures on this record" in summary["detail"]
    assert alert is None


def test_invalid_parameters_are_refused():
    with pytest.raises(ValueError):
        statistical_analysis(ordinary(), REFERENCE, PARTIES, min_samples=1)
    with pytest.raises(ValueError):
        synthetic_dataset(["party:PA"])


# Through the real evidence workflow


@pytest.fixture(scope="module")
def seeded(tmp_path_factory) -> Iterator[tuple[Path, Session]]:
    root = tmp_path_factory.mktemp("anomaly")
    previous = Path.cwd()
    os.chdir(root)
    try:
        report = anomaly_demo.seed_command(anomaly_demo.DEFAULT_DIR)
        factory, storage = anomaly_demo._open(root / anomaly_demo.DEFAULT_DIR)
        with factory() as db:
            yield root, db, report, storage
        factory.kw["bind"].dispose()
    finally:
        os.chdir(previous)


def _submissions(db: Session) -> list[EvidenceSubmission]:
    db.expire_all()
    return list(
        db.scalars(select(EvidenceSubmission).where(EvidenceSubmission.election_id == ELECTION.id))
    )


def _current_alerts(db: Session, submission: EvidenceSubmission) -> set[str]:
    run = service.latest_validation(db, submission.id).report["analysis_run_id"]
    return {
        AlertCategory(a.category).value
        for a in db.scalars(select(AnomalyAlert).where(AnomalyAlert.submission_id == submission.id))
        if str(a.analysis_run_id) == run
    }


def test_seeding_goes_through_the_workflow_and_matches_the_offline_scores(seeded, results):
    _, db, report, _ = seeded
    rows = _submissions(db)
    assert len(rows) == len(DATASET) and all(service.is_synthetic(s) for s in rows)
    assert all(s.provenance["directory_is_demo"] for s in rows)
    statuses = [EvidenceStatus(s.workflow_status) for s in rows]
    assert statuses.count(EvidenceStatus.VERIFIED) == ORDINARY_REFERENCE
    assert EvidenceStatus.REJECTED not in statuses
    for row in report.awaiting_review:
        offline = results[row["name"]]["summary"]
        assert row["anomaly_score"] == offline["anomaly_score"], row["name"]
        assert row["arithmetic_passed"] is True


def test_anomalies_create_review_alerts_distinct_from_other_checks(seeded):
    _, db, report, _ = seeded
    by_name = {row["name"]: row for row in report.awaiting_review}
    for record in DATASET:
        if record.reviewed:
            continue
        row = by_name[record.name]
        submission = db.get(EvidenceSubmission, uuid.UUID(row["submission_id"]))
        alerts = _current_alerts(db, submission)
        validation = service.latest_validation(db, submission.id)
        assert validation.passed and not validation.report["failed"]  # arithmetic is fine
        assert "submission_discrepancy" not in alerts  # one submission per unit
        if record.injected:
            assert alerts == {"statistical"}
            assert submission.workflow_status == EvidenceStatus.FLAGGED_FOR_REVIEW
        else:
            assert alerts == set()
            assert submission.workflow_status == EvidenceStatus.CROSS_CHECKED


def test_reviewers_keep_the_final_decision_on_a_statistical_outlier(seeded):
    _, db, report, _ = seeded
    row = next(r for r in report.awaiting_review if r["name"] == "SYNTHETIC-ODD-03")
    submission = db.get(EvidenceSubmission, uuid.UUID(row["submission_id"]))
    settings = get_settings()
    first = Principal(user_id=uuid.uuid4(), roles=[Role.REVIEWER])
    second = Principal(user_id=uuid.uuid4(), roles=[Role.REVIEWER])
    service.review(db, submission, first, "start", None, settings)
    with pytest.raises(AppError) as missing:
        service.review(db, submission, first, "approve", None, settings)
    assert missing.value.code == "notes_required"
    notes = "Checked the image: the unit is a party stronghold, figures match the sheet."
    service.review(db, submission, first, "approve", notes, settings)
    service.review(db, submission, second, "approve", notes, settings)
    db.refresh(submission)
    assert submission.workflow_status == EvidenceStatus.VERIFIED


def test_seeding_is_idempotent(seeded):
    root, db, _, storage = seeded
    again = anomaly_demo.seed_synthetic(db, storage, get_settings(), DIRECTORY)
    assert again.reviewed == 0 and not again.awaiting_review
    assert again.skipped == len(DATASET)
    assert len(_submissions(db)) == len(DATASET)


def test_synthetic_and_genuine_records_never_reference_each_other(seeded):
    root, db, _, storage = seeded
    settings = get_settings()
    pipeline = DemoPipeline(db, storage, settings, DIRECTORY, ELECTION)
    # Every demo unit already holds a synthetic record, so the genuine one shares a unit.
    unit = sorted(DIRECTORY.list_all_polling_units(), key=lambda u: u.code)[0]
    genuine_values = {
        "polling_unit_code": unit.code,
        "election_label": ELECTION.election_label,
        **BY_NAME["SYNTHETIC-ODD-01"].values,
    }
    genuine = pipeline.accepted(unit.id, AGENT, genuine_values, seed=99)
    assert not service.is_synthetic(genuine)
    statistical = service.latest_validation(db, genuine.id).report["statistical_analysis"]
    # 37 verified synthetic records exist in this election; none is used for a genuine one,
    # so these very unusual figures raise no statistical alert.
    assert statistical["reference_records"] == 0
    assert statistical["status"] == "insufficient_data"
    assert "statistical" not in _current_alerts(db, genuine)

    # The seeder and cleanup now refuse: the store holds a record they did not make.
    with pytest.raises(SystemExit, match="not synthetic"):
        anomaly_demo.seed_synthetic(db, storage, settings, DIRECTORY)
    previous = Path.cwd()
    os.chdir(root)
    try:
        with pytest.raises(SystemExit, match="did not make"):
            anomaly_demo.cleanup_command(anomaly_demo.DEFAULT_DIR)
    finally:
        os.chdir(previous)
    assert (root / anomaly_demo.DEFAULT_DIR / anomaly_demo.DATABASE_FILE).exists()


def test_synthetic_records_are_refused_outside_demo_elections(seeded, tmp_path):
    _, db, _, storage = seeded
    real = ELECTION.model_copy(update={"is_demo": False})
    unit = DIRECTORY.get_polling_unit(DIRECTORY.list_all_polling_units()[0].id)
    upload = service.Upload(
        data=b"irrelevant",
        filename="x.jpg",
        content_type="image/jpeg",
        idempotency_key=uuid.uuid4(),
        captured_at=None,
        client_sha256=None,
        client_info={"capture_source": service.SYNTHETIC_SOURCE},
    )
    with pytest.raises(AppError) as refused:
        service.ingest(db, storage, get_settings(), AGENT, real, unit, upload)
    assert refused.value.code == "synthetic_not_allowed"
    with pytest.raises(SystemExit, match="demo directory"):
        anomaly_demo.assert_seedable(db, get_settings(), DIRECTORY, real)
    production = get_settings().model_copy(update={"app_env": "production"})
    with pytest.raises(SystemExit, match="production"):
        anomaly_demo.assert_seedable(db, production, DIRECTORY, ELECTION)


# Safe seeding and cleanup of the dedicated folder


def test_folders_not_made_by_the_tool_are_never_written_or_deleted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    precious = tmp_path / "var" / "preview"
    precious.mkdir(parents=True)
    (precious / "preview.sqlite3").write_text("real data")
    with pytest.raises(SystemExit, match="not created by this tool"):
        anomaly_demo.seed_command("var/preview")
    with pytest.raises(SystemExit, match="not created by this tool"):
        anomaly_demo.cleanup_command("var/preview")
    with pytest.raises(SystemExit, match="must be inside"):
        anomaly_demo.cleanup_command("../elsewhere")
    with pytest.raises(SystemExit, match="must be inside"):
        anomaly_demo.cleanup_command("var")
    assert (precious / "preview.sqlite3").read_text() == "real data"


def test_cleanup_removes_only_its_own_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ours = tmp_path / "var" / "anomaly-demo"
    ours.mkdir(parents=True)
    (ours / anomaly_demo.MARKER).write_text("marker")
    neighbour = tmp_path / "var" / "preview.sqlite3"
    neighbour.write_text("keep")
    assert anomaly_demo.cleanup_command("var/anomaly-demo") is True
    assert not ours.exists() and neighbour.read_text() == "keep"
    assert anomaly_demo.cleanup_command("var/anomaly-demo") is False
