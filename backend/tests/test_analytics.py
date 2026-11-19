"""Hierarchical aggregation. Every submission is generated DEMONSTRATION/TEST DATA driven
through the real evidence workflow against the fictional demo register."""

import asyncio
import random
import threading
import uuid
from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.analytics import demo_seed, queries
from app.analytics.demo_seed import AGENT, OBSERVER, REVIEWERS, DemoPipeline, demo_values
from app.analytics.events import AnalyticsBroker, broker, stream_events
from app.analytics.policy import SubmissionState, count_independent, decide
from app.analytics.refresh import ENTITY_PU_RESULT
from app.analytics.registry import registry_for
from app.core.config import get_settings
from app.core.security import Principal
from app.db.enums import EvidenceStatus, PollingUnitResultStatus, Role
from app.db.models import PollingUnitResult
from app.directory.repository import get_directory
from app.evidence import service
from app.evidence.audit import load_chain, verify_chain
from app.evidence.db import create_dev_engine, get_evidence_db
from app.evidence.storage import LocalStorage
from app.evidence.templates import party_key
from app.main import create_app
from tests.evidence_support import actor

DIRECTORY = get_directory()
ELECTION = next(e for e in DIRECTORY.list_elections() if e.election_label == "PRESIDENTIAL")
REGISTRY = registry_for(DIRECTORY, ELECTION)
PARTIES = [party_key(p.code) for p in ELECTION.parties]

def _units_of_ward(ward_id):
    return sorted(REGISTRY.units_by_ward[ward_id], key=lambda i: REGISTRY.units[i].code)

def _big_ward():
    return next(w for w, units in REGISTRY.units_by_ward.items() if len(units) >= 3)

def values_for(unit_id, seed=0, **overrides):
    unit = next(u for u in DIRECTORY.list_all_polling_units() if u.id == unit_id)
    values = demo_values(unit, ELECTION, random.Random(f"{unit_id}/{seed}"))
    values.update(overrides)
    return values

def shifted(values, amount=10):
    """Same sheet with votes moved between the first two parties (still consistent)."""
    other = dict(values)
    move = min(amount, other[PARTIES[1]])
    other[PARTIES[0]] += move
    other[PARTIES[1]] -= move
    return other

class World:
    def __init__(self, factory, storage) -> None:
        self.factory = factory
        self.storage = storage
        self.settings = get_settings()
        self.db: Session = factory()
        self.pipe = DemoPipeline(self.db, storage, self.settings, DIRECTORY, ELECTION)
        self._seed = 0

    def next_seed(self) -> int:
        self._seed += 1
        return self._seed

    def accepted(self, unit_id, values, who: Principal = OBSERVER):
        return self.pipe.accepted(unit_id, who, values, self.next_seed())

    def verified(self, unit_id, values, who: Principal = OBSERVER):
        submission = self.accepted(unit_id, values, who)
        self.pipe.verify(submission)
        return submission

    def ctx(self) -> queries.Context:
        self.db.expire_all()
        return queries.context(self.db, DIRECTORY, ELECTION.id)

    def row(self, unit_id) -> PollingUnitResult | None:
        self.db.expire_all()
        return self.db.scalar(
            select(PollingUnitResult).where(
                PollingUnitResult.election_id == ELECTION.id,
                PollingUnitResult.polling_unit_id == unit_id,
            )
        )

@pytest.fixture()
def world(tmp_path) -> Iterator[World]:
    get_settings.cache_clear()
    engine = create_dev_engine(str(tmp_path / "analytics.sqlite3"))
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    w = World(factory, LocalStorage(str(tmp_path / "storage"), "evidence"))
    yield w
    w.db.close()

@pytest.fixture()
def client(world) -> Iterator[TestClient]:
    app = create_app()

    def override():
        with world.factory() as session:
            yield session

    app.dependency_overrides[get_evidence_db] = override
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client

def party_votes(stream) -> dict[str, int]:
    return {party_key(p.code): p.votes for p in stream.parties}

def summed(values_list) -> dict[str, int]:
    return {key: sum(v[key] for v in values_list) for key in PARTIES}

def _state(**kw):
    base = dict(
        id=uuid.uuid4(),
        submitted_by=uuid.uuid4(),
        status=EvidenceStatus.CROSS_CHECKED,
        received_at=datetime(2026, 11, 18, 9),
        status_changed_at=datetime(2026, 11, 18, 9),
        original_sha256=uuid.uuid4().hex * 2,
        perceptual_hash=None,
        validation_passed=True,
        result_hash="a" * 64,
        values={"party:PA": 10, "total_valid_votes": 10},
    )
    base.update(kw)
    return SubmissionState(**base)

def test_policy_counts_a_unit_once_and_excludes_unresolved_records():
    agreeing = [_state(), _state(), _state(status=EvidenceStatus.VERIFIED)]
    outcome = decide(agreeing)
    assert outcome.status == PollingUnitResultStatus.VERIFIED
    assert outcome.reported_metrics == {"party:PA": 10, "total_valid_votes": 10}
    assert outcome.accepted_count == 3

    conflict = decide([_state(status=EvidenceStatus.VERIFIED), _state(result_hash="b" * 64)])
    assert conflict.status == PollingUnitResultStatus.CONFLICT
    assert conflict.reported_metrics == {} and conflict.verified_metrics == {}

    pending = decide([_state(status=EvidenceStatus.EXTRACTED, validation_passed=None)])
    assert pending.status == PollingUnitResultStatus.PENDING
    failed = decide([_state(status=EvidenceStatus.FLAGGED_FOR_REVIEW, validation_passed=False)])
    assert failed.status == PollingUnitResultStatus.PENDING and failed.has_flagged
    rejected = decide([_state(status=EvidenceStatus.REJECTED)])
    assert rejected.status == PollingUnitResultStatus.NOT_REPORTING
    assert rejected.rejected_count == 1

def test_independence_ignores_same_account_and_duplicate_images():
    person = uuid.uuid4()
    same_file = "c" * 64
    items = [
        _state(submitted_by=person, original_sha256=same_file, perceptual_hash="ffff0000ffff0000"),
        _state(submitted_by=person),
        _state(original_sha256=same_file),
        _state(perceptual_hash="ffff0000ffff0001"),
        _state(perceptual_hash="0000ffff0000ffff"),
    ]
    items = [
        replace(item, received_at=datetime(2026, 11, 18, 9, minute))
        for minute, item in enumerate(items)
    ]
    assert count_independent(items) == 2
    # Arrival order decides which copy counts; the total never exceeds distinct sources.
    assert count_independent(list(reversed(items))) <= 4

def test_polling_unit_to_ward_aggregation(world):
    ward_id = _big_ward()
    first, second, third = _units_of_ward(ward_id)[:3]
    v1, v2 = values_for(first), values_for(second)
    world.verified(first, v1)
    world.accepted(second, v2)

    ward = queries.area(world.ctx(), "ward", ward_id)
    cov = ward.summary.coverage
    assert cov.expected_polling_units == len(REGISTRY.units_by_ward[ward_id])
    assert cov.polling_units_with_submissions == 2
    assert cov.reporting_polling_units == 2
    assert cov.verified_polling_units == 1
    assert cov.pending_polling_units == 1
    assert party_votes(ward.reported) == summed([v1, v2])
    assert party_votes(ward.verified) == summed([v1])
    assert ward.reported.total_valid_votes == v1["total_valid_votes"] + v2["total_valid_votes"]
    by_unit = {c.area.id: c.coverage for c in ward.children}
    assert by_unit[third].reporting_polling_units == 0
    assert by_unit[first].verified_polling_units == 1

def _assert_additive(parent, children):
    cov = parent.summary.coverage
    for name in (
        "expected_polling_units",
        "reporting_polling_units",
        "verified_polling_units",
        "pending_polling_units",
        "flagged_polling_units",
        "conflict_polling_units",
        "submission_count",
    ):
        assert getattr(cov, name) == sum(getattr(c.coverage, name) for c in children), name

def test_ward_lga_state_national_totals_add_up(world):
    # One accepted unit in each of several wards, LGAs and states, some verified.
    picked = []
    for lga_ids in REGISTRY.lgas_by_state.values():
        for lga_id in lga_ids:
            ward_id = REGISTRY.wards_by_lga[lga_id][0]
            picked.append(_units_of_ward(ward_id)[0])
    expected_reported, expected_verified = [], []
    for index, unit_id in enumerate(picked):
        values = values_for(unit_id)
        if index % 2 == 0:
            world.verified(unit_id, values)
            expected_verified.append(values)
        else:
            world.accepted(unit_id, values)
        expected_reported.append(values)

    ctx = world.ctx()
    national = queries.area(ctx, "national", None)
    assert national.summary.coverage.expected_polling_units == len(REGISTRY.units) == 44
    assert party_votes(national.reported) == summed(expected_reported)
    assert party_votes(national.verified) == summed(expected_verified)
    _assert_additive(national, national.children)
    assert party_votes(national.reported) == {
        key: sum(
            party_votes(queries.area(ctx, "state", s.area.id).reported)[key]
            for s in national.children
        )
        for key in PARTIES
    }

    for state_summary in national.children:
        state = queries.area(ctx, "state", state_summary.area.id)
        _assert_additive(state, state.children)
        assert state.summary.coverage == state_summary.coverage
        for lga_summary in state.children:
            lga = queries.area(ctx, "lga", lga_summary.area.id)
            _assert_additive(lga, lga.children)
            lga_votes = party_votes(lga.reported)
            ward_votes = [
                party_votes(queries.area(ctx, "ward", w.area.id).reported) for w in lga.children
            ]
            assert lga_votes == {k: sum(w[k] for w in ward_votes) for k in PARTIES}
            for ward_summary in lga.children:
                ward = queries.area(ctx, "ward", ward_summary.area.id)
                _assert_additive(ward, ward.children)

def test_duplicate_submissions_are_counted_once(world):
    unit_id = _units_of_ward(_big_ward())[0]
    values = values_for(unit_id)
    first = world.accepted(unit_id, values, OBSERVER)
    world.accepted(unit_id, values, AGENT)
    world.accepted(unit_id, values, demo_seed.SECOND_OBSERVER)
    # The same observer re-sending the same file is recognised and not stored again.
    again = world.pipe.submit(unit_id, OBSERVER, values, seed=1)
    assert again.id == first.id

    row = world.row(unit_id)
    assert row.status == PollingUnitResultStatus.REPORTED
    assert row.submission_count == 3
    assert row.independent_count == 3
    assert len(row.contributing_submission_ids) == 3
    national = queries.area(world.ctx(), "national", None)
    assert national.summary.coverage.reporting_polling_units == 1
    assert party_votes(national.reported) == summed([values])
    assert national.reported.polling_units_included == 1
    count = world.db.scalar(select(func.count()).select_from(PollingUnitResult))
    assert count == 1

def test_conflicting_submissions_are_kept_shown_and_excluded(world, client):
    unit_id = _units_of_ward(_big_ward())[0]
    values = values_for(unit_id)
    first = world.accepted(unit_id, values, OBSERVER)
    second = world.accepted(unit_id, shifted(values), AGENT)

    row = world.row(unit_id)
    assert row.status == PollingUnitResultStatus.CONFLICT
    assert row.distinct_results == 2
    assert sorted(row.source_submission_ids) == sorted([str(first.id), str(second.id)])
    assert row.contributing_submission_ids == []

    national = queries.area(world.ctx(), "national", None)
    cov = national.summary.coverage
    assert cov.reporting_polling_units == 1 and cov.conflict_polling_units == 1
    assert national.reported.polling_units_included == 0
    assert sum(party_votes(national.reported).values()) == 0
    assert next(a for a in national.alerts if a.kind == "unresolved_discrepancies").count == 1

    listed = client.get(
        "/api/v1/analytics/discrepancies",
        params={"election_id": str(ELECTION.id), "kind": "conflict"},
    ).json()
    assert [item["id"] for item in listed["items"]] == [str(unit_id)]

    detail = client.get(
        f"/api/v1/analytics/polling-units/{unit_id}", params={"election_id": str(ELECTION.id)}
    ).json()
    assert len(detail["source_records"]) == 2
    assert not any(r["contributes"] for r in detail["source_records"])
    assert len({r["result_fingerprint"] for r in detail["source_records"]}) == 2

    # Reviewers resolve the disagreement by rejecting the wrong submission.
    world.pipe.review(second, REVIEWERS[0], "start", None)
    world.pipe.review(second, REVIEWERS[0], "reject", "Figures do not match the photo.")
    row = world.row(unit_id)
    assert row.status == PollingUnitResultStatus.REPORTED
    assert row.contributing_submission_ids == [str(first.id)]
    assert party_votes(queries.area(world.ctx(), "national", None).reported) == summed([values])

def test_reported_and_verified_streams_are_separate(world):
    ward = _units_of_ward(_big_ward())
    verified_values, reported_values, review_values = (values_for(u) for u in ward[:3])
    world.verified(ward[0], verified_values)
    world.accepted(ward[1], reported_values)
    under_review = world.accepted(ward[2], review_values)
    world.pipe.review(under_review, REVIEWERS[0], "start", None)

    national = queries.area(world.ctx(), "national", None)
    assert party_votes(national.reported) == summed(
        [verified_values, reported_values, review_values]
    )
    assert party_votes(national.verified) == summed([verified_values])
    assert national.verified.polling_units_included == 1
    assert national.reported.polling_units_included == 3

def test_rejected_records_are_excluded(world):
    unit_id = _units_of_ward(_big_ward())[0]
    submission = world.accepted(unit_id, values_for(unit_id))
    world.pipe.review(submission, REVIEWERS[0], "start", None)
    world.pipe.review(submission, REVIEWERS[0], "reject", "Not a result sheet.")

    row = world.row(unit_id)
    assert row.status == PollingUnitResultStatus.NOT_REPORTING
    assert row.rejected_count == 1 and row.submission_count == 0
    national = queries.area(world.ctx(), "national", None)
    assert national.summary.coverage.reporting_polling_units == 0
    assert national.summary.coverage.rejected_submission_count == 1
    assert sum(party_votes(national.reported).values()) == 0

def test_unresolved_records_never_reach_verified_totals(world):
    unit_id = _units_of_ward(_big_ward())[0]
    values = values_for(unit_id)
    world.verified(unit_id, values)
    assert world.row(unit_id).status == PollingUnitResultStatus.VERIFIED

    # A later, validated submission with different figures reopens the unit.
    world.accepted(unit_id, shifted(values), AGENT)
    row = world.row(unit_id)
    assert row.status == PollingUnitResultStatus.CONFLICT
    assert row.verified_result_hash is None
    national = queries.area(world.ctx(), "national", None)
    assert national.summary.coverage.verified_polling_units == 0
    assert sum(party_votes(national.verified).values()) == 0

    # Failed validation and pending processing are not in either total.
    other_ward = _units_of_ward(_big_ward())
    bad = values_for(other_ward[1])
    bad["total_valid_votes"] += 3
    world.accepted(other_ward[1], bad)
    world.pipe.submit(other_ward[2], OBSERVER, values_for(other_ward[2]), seed=99)
    assert world.row(other_ward[1]).status == PollingUnitResultStatus.PENDING
    assert world.row(other_ward[2]).status == PollingUnitResultStatus.PENDING
    assert world.row(other_ward[1]).has_flagged

def test_reporting_and_verification_coverage_use_the_register(world):
    ward_id = next(w for w, units in REGISTRY.units_by_ward.items() if len(units) == 3)
    units = _units_of_ward(ward_id)
    world.verified(units[0], values_for(units[0]))
    world.accepted(units[1], values_for(units[1]))

    ward = queries.area(world.ctx(), "ward", ward_id).summary.coverage
    assert ward.expected_polling_units == 3
    assert ward.reporting_coverage_pct == 66.7
    assert ward.verification_coverage_pct == 33.3
    assert ward.reporting_label == "2 / 3 polling units reporting, 66.7% coverage"
    assert ward.verification_label == "1 / 3 polling units verified, 33.3% verification coverage"

    lga_id = REGISTRY.wards[ward_id].lga_id
    lga = queries.area(world.ctx(), "lga", lga_id).summary.coverage
    assert lga.expected_polling_units == REGISTRY.expected_by_lga[lga_id]
    assert lga.reporting_coverage_pct == round(200 / REGISTRY.expected_by_lga[lga_id], 1)

    # Wards really differ in size, so a uniform assumption would be wrong.
    assert len({len(u) for u in REGISTRY.units_by_ward.values()}) > 1
    assert len({len(w) for w in REGISTRY.wards_by_lga.values()}) > 1

def test_authorised_correction_recalculates_aggregation(world):
    unit_id = _units_of_ward(_big_ward())[0]
    values = values_for(unit_id)
    submission = world.accepted(unit_id, values)
    first_revision = world.row(unit_id).revision

    world.pipe.review(submission, REVIEWERS[0], "start", None)
    world.pipe.review(submission, REVIEWERS[0], "request_correction", "Party A misread.")
    assert world.row(unit_id).status == PollingUnitResultStatus.PENDING

    corrected = shifted(values, 5)
    service.correct(
        world.db,
        submission,
        ELECTION,
        REVIEWERS[0],
        [
            service.Correction(PARTIES[0], corrected[PARTIES[0]], "Re-read from the photo"),
            service.Correction(PARTIES[1], corrected[PARTIES[1]], "Re-read from the photo"),
        ],
    )
    world.pipe.validate(submission, REVIEWERS[0])
    row = world.row(unit_id)
    assert row.status == PollingUnitResultStatus.REPORTED
    assert row.revision > first_revision
    assert party_votes(queries.area(world.ctx(), "national", None).reported) == summed([corrected])

    chain = load_chain(world.db, row.id, entity_type=ENTITY_PU_RESULT)
    assert [e.details["status"] for e in chain][-1] == "reported"
    assert "pending" in [e.details["status"] for e in chain]
    assert verify_chain(chain).valid

def test_changes_are_published_after_commit_only(world):
    unit_id = _units_of_ward(_big_ward())[0]
    start = broker.last_id
    world.accepted(unit_id, values_for(unit_id))
    events = [
        e.payload for e in broker.since(start) if e.payload["polling_unit_id"] == str(unit_id)
    ]
    assert events, "expected change notifications"
    last = events[-1]
    unit = REGISTRY.units[unit_id]
    assert last["status"] == "reported"
    assert last["ward_id"] == str(unit.ward_id)
    assert last["lga_id"] == str(unit.lga_id)
    assert last["state_id"] == str(unit.state_id)
    assert last["election_id"] == str(ELECTION.id)
    assert "submitted_by" not in last

    # A rolled-back change publishes nothing.
    before = broker.last_id
    submission = world.db.get(
        service.EvidenceSubmission, uuid.UUID(world.row(unit_id).source_submission_ids[0])
    )
    submission.workflow_status = EvidenceStatus.REJECTED
    world.db.flush()
    world.db.rollback()
    assert broker.last_id == before

def test_event_stream_replays_and_streams_matching_events():
    local = AnalyticsBroker()
    election = str(uuid.uuid4())

    async def run():
        subscription = local.subscribe()
        local.publish({"election_id": election, "polling_unit_id": "a"})
        local.publish({"election_id": "other", "polling_unit_id": "b"})
        calls = {"n": 0}

        async def disconnected():
            calls["n"] += 1
            return calls["n"] > 3

        chunks = []
        async for chunk in stream_events(
            local,
            subscription,
            disconnected,
            election_id=election,
            last_event_id=0,
            heartbeat_seconds=0.01,
        ):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(run())
    body = "".join(chunks)
    assert body.startswith("retry: 5000")
    assert body.count('"polling_unit_id":"a"') >= 1
    assert '"polling_unit_id":"b"' not in body
    assert local.subscriber_count == 0

def test_concurrent_submissions_for_one_unit_produce_one_row(world):
    unit_id = _units_of_ward(_big_ward())[0]
    values = values_for(unit_id)
    errors: list[BaseException] = []
    people = [OBSERVER, AGENT, demo_seed.SECOND_OBSERVER]

    def work(index: int) -> None:
        try:
            with world.factory() as db:
                pipe = DemoPipeline(db, world.storage, world.settings, DIRECTORY, ELECTION)
                pipe.accepted(unit_id, people[index], values, seed=500 + index)
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors, errors

    rows = world.db.scalars(
        select(PollingUnitResult).where(PollingUnitResult.polling_unit_id == unit_id)
    ).all()
    assert len(rows) == 1
    assert rows[0].submission_count == 3
    assert rows[0].status == PollingUnitResultStatus.REPORTED
    national = queries.area(world.ctx(), "national", None)
    assert party_votes(national.reported) == summed([values])

def test_provenance_traces_totals_to_source_records(world, client):
    unit_id = _units_of_ward(_big_ward())[0]
    submission = world.verified(unit_id, values_for(unit_id))
    params = {"election_id": str(ELECTION.id)}

    national = client.get("/api/v1/analytics/national", params=params).json()
    assert national["data_status"] == "demonstration"
    assert national["demo_label"] == "Sample data. Not an official election result."
    assert "not INEC declarations" in national["notice"]
    assert national["provenance"]["registry_source"]["kind"] == "demo"
    assert national["summary"]["last_updated_at"]
    assert national["level"] == "national"
    trace = client.get(national["provenance"]["source_records_path"]).json()
    verified = [u for u in trace["items"] if u["status"] == "verified"]
    assert [u["id"] for u in verified] == [str(unit_id)]

    detail = client.get(f"/api/v1/analytics/polling-units/{unit_id}", params=params).json()
    [record] = detail["source_records"]
    assert record["submission_id"] == str(submission.id)
    assert record["contributes"] is True
    assert record["result_fingerprint"] == detail["unit"]["verified_result_hash"]
    assert detail["verification"]["approvals_on_verified_result"] == 2
    assert detail["verification"]["required_approvals"] == 2
    assert [c["level"] for c in detail["breadcrumbs"]] == [
        "national",
        "state",
        "lga",
        "ward",
        "polling_unit",
    ]

def test_public_read_only_access_without_private_details(world, client):
    unit_id = _units_of_ward(_big_ward())[0]
    world.verified(unit_id, values_for(unit_id))
    params = {"election_id": str(ELECTION.id)}
    unit = REGISTRY.units[unit_id]
    paths = [
        "/api/v1/analytics/national",
        "/api/v1/analytics/states",
        f"/api/v1/analytics/states/{unit.state_id}",
        f"/api/v1/analytics/lgas/{unit.lga_id}",
        f"/api/v1/analytics/wards/{unit.ward_id}",
        f"/api/v1/analytics/polling-units/{unit_id}",
        "/api/v1/analytics/polling-units",
        "/api/v1/analytics/reporting-coverage",
        "/api/v1/analytics/verification-coverage",
        "/api/v1/analytics/party-results",
        "/api/v1/analytics/discrepancies",
        "/api/v1/analytics/progress",
    ]
    private = [str(OBSERVER.user_id), *(str(r.user_id) for r in REVIEWERS), "originals/", "storage"]
    for path in paths:
        response = client.get(path, params=params)
        assert response.status_code == 200, (path, response.text)
        assert not any(secret in response.text for secret in private), path
        assert client.post(path, params=params, json={}).status_code in (404, 405), path

    rebuild = "/api/v1/admin/analytics/rebuild"
    assert client.post(rebuild, params=params).status_code == 401
    assert client.post(rebuild, params=params, headers=actor("observer").headers).status_code == 403
    assert client.post(rebuild, params=params, headers=actor("reviewer").headers).status_code == 403
    ok = client.post(rebuild, params=params, headers=actor("system_admin").headers)
    assert ok.status_code == 200 and ok.json()["polling_units_changed"] == 0

def test_query_parameters_are_validated(client):
    base = "/api/v1/analytics"
    assert client.get(f"{base}/national").status_code == 422
    assert client.get(f"{base}/national", params={"election_id": "x"}).status_code == 422
    assert (
        client.get(f"{base}/national", params={"election_id": str(uuid.uuid4())}).status_code == 404
    )
    params = {"election_id": str(ELECTION.id)}
    assert client.get(f"{base}/states/{uuid.uuid4()}", params=params).status_code == 404
    assert (
        client.get(f"{base}/polling-units", params={**params, "page_size": 1000}).status_code == 422
    )
    some_state, some_lga = next(iter(REGISTRY.lgas_by_state.items()))
    two = {**params, "state_id": str(some_state), "lga_id": str(some_lga[0])}
    assert client.get(f"{base}/party-results", params=two).status_code == 422
    assert (
        client.get(f"{base}/discrepancies", params={**params, "kind": "fraud"}).status_code == 422
    )
    assert (
        client.get(f"{base}/reporting-coverage", params={**params, "level": "lga"}).status_code
        == 422
    )
    assert (
        client.get(f"{base}/updates", params={"election_id": str(uuid.uuid4())}).status_code == 404
    )

def test_demo_dataset_is_labelled_and_internally_consistent(world):
    created = demo_seed.seed(world.db, world.storage, world.settings, DIRECTORY, ELECTION)
    assert {"verified", "reported", "conflict", "pending", "flagged_arithmetic"} <= set(created)
    national = queries.area(world.ctx(), "national", None)
    cov = national.summary.coverage
    assert national.demo_label == "Sample data. Not an official election result."
    assert cov.expected_polling_units == 44
    assert cov.reporting_polling_units == (
        created["verified"]
        + created["verified_two_sources"]
        + created["reported"]
        + created["under_review"]
        + created["conflict"]
    )
    assert cov.verified_polling_units == created["verified"] + created["verified_two_sources"]
    assert cov.conflict_polling_units == created["conflict"]
    assert national.reported.total_valid_votes == sum(p.votes for p in national.reported.parties)
    assert national.verified.total_votes_cast == (
        national.verified.total_valid_votes + national.verified.rejected_votes
    )
    _assert_additive(national, national.children)
    # Seeding twice adds nothing.
    assert (
        sum(demo_seed.seed(world.db, world.storage, world.settings, DIRECTORY, ELECTION).values())
        == 0
    )

def test_demo_seed_refuses_non_demo_elections(world):
    real = ELECTION.model_copy(update={"is_demo": False})
    with pytest.raises(SystemExit):
        demo_seed.seed(world.db, world.storage, world.settings, DIRECTORY, real)

def test_roles_cannot_be_used_to_set_status(client):
    # There is no analytics write route other than the admin rebuild, which takes no body.
    schema = client.get("/openapi.json").json()["paths"]
    analytics = {p: ops for p, ops in schema.items() if "/analytics" in p}
    writes = [
        (p, m)
        for p, ops in analytics.items()
        for m in ops
        if m in ("post", "put", "patch", "delete")
    ]
    assert writes == [("/api/v1/admin/analytics/rebuild", "post")]
    assert "requestBody" not in analytics["/api/v1/admin/analytics/rebuild"]["post"]
    assert Role.SYSTEM_ADMIN
