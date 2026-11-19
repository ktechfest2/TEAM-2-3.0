"""End-to-end evidence workflow through the HTTP API. All images and OCR output are
generated TEST DATA, processed with a fake OCR provider and a temporary SQLite store."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.models import EvidenceImage
from app.evidence.db import create_dev_engine, get_evidence_db
from app.evidence.hashing import sha256_bytes
from app.evidence.ocr import get_ocr_provider
from app.evidence.storage import LocalStorage, get_storage
from app.main import create_app
from tests.evidence_support import (
    FakeOcr,
    actor,
    demo_targets,
    make_sheet_image,
    reencode,
    sheet_lines,
    sheet_tokens,
)

ELECTION, UNIT, OTHER_UNIT = demo_targets()

class Env:
    def __init__(self, client: TestClient, ocr: FakeOcr, factory, storage_root) -> None:
        self.client = client
        self.ocr = ocr
        self.factory = factory
        self.storage_root = storage_root

    def submit(
        self,
        who,
        data: bytes | None = None,
        *,
        key: str | None = None,
        unit=UNIT,
        filename="sheet.jpg",
        mime="image/jpeg",
        headers=None,
        **form,
    ):
        data = make_sheet_image(1) if data is None else data
        return self.client.post(
            "/api/v1/evidence",
            headers={**who.headers, "Idempotency-Key": key or str(uuid.uuid4()), **(headers or {})},
            data={"election_id": str(ELECTION.id), "polling_unit_id": str(unit.id), **form},
            files={"file": (filename, data, mime)},
        )

    def submitted(self, who, seed=1, lines=None, unit=UNIT, **ocr) -> str:
        response = self.submit(who, make_sheet_image(seed), unit=unit)
        assert response.status_code == 201, response.text
        submission_id = response.json()["item"]["id"]
        self.ocr.tokens = sheet_tokens(lines or sheet_lines(unit.code), **ocr)
        processed = self.client.post(
            f"/api/v1/evidence/{submission_id}/process", headers=who.headers
        )
        assert processed.status_code == 200, processed.text
        return submission_id

    def get(self, who, path: str):
        return self.client.get(f"/api/v1/evidence{path}", headers=who.headers)

    def post(self, who, path: str, json=None):
        return self.client.post(f"/api/v1/evidence{path}", headers=who.headers, json=json)

    def status(self, who, submission_id: str) -> str:
        return self.get(who, f"/{submission_id}").json()["status"]

@pytest.fixture()
def env(tmp_path) -> Iterator[Env]:
    get_settings.cache_clear()
    app = create_app()
    engine = create_dev_engine(str(tmp_path / "evidence.sqlite3"))
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    storage = LocalStorage(str(tmp_path / "storage"), "evidence")
    ocr = FakeOcr()

    def db_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_evidence_db] = db_override
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_ocr_provider] = lambda: ocr
    with TestClient(app, raise_server_exceptions=False) as client:
        yield Env(client, ocr, factory, tmp_path / "storage")

def test_unauthenticated_and_unauthorised_uploads_are_refused(env):
    no_auth = env.client.post("/api/v1/evidence", data={}, files={"file": ("a.jpg", b"x")})
    assert no_auth.status_code == 401
    auditor = actor("auditor")
    assert env.submit(auditor).status_code == 403
    nobody = actor()
    assert env.submit(nobody).status_code == 403

def test_upload_is_fingerprinted_before_processing(env):
    observer = actor("observer")
    data = make_sheet_image(5)
    response = env.submit(
        observer, data, captured_at="2026-11-18T09:30:00+01:00", capture_source="camera"
    )
    assert response.status_code == 201, response.text
    body = response.json()
    item = body["item"]
    assert body["created"] is True
    assert item["status"] == "received"
    assert item["original_sha256"] == sha256_bytes(data)
    assert item["captured_at"].startswith("2026-11-18T08:30:00")
    assert item["captured_at"] != item["received_at"]
    assert item["submitted_by"] is None  # submitters never receive account identifiers
    assert item["is_mine"] is True
    assert item["images"][0]["kind"] == "original"
    assert item["provenance"]["capture_source"] == "camera"
    assert "INEC" in item["status_notice"]

    stored = list(env.storage_root.rglob("*.jpg"))
    assert len(stored) == 1 and stored[0].read_bytes() == data
    assert oct(stored[0].stat().st_mode & 0o777) == "0o600"

    audit = env.get(observer, f"/{item['id']}/audit").json()
    assert [e["action"] for e in audit["events"]][:2] == ["evidence.received", "evidence.hashed"]
    assert audit["chain_valid"] is True

def test_invalid_files_are_rejected(env):
    observer = actor("observer")
    fake = env.submit(observer, b"GIF89a" + b"\x00" * 2000, filename="sheet.jpg")
    assert fake.status_code == 415
    mismatch = env.submit(observer, make_sheet_image(1, fmt="PNG"), filename="sheet.jpg")
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "type_mismatch"
    small = env.submit(observer, make_sheet_image(1, size=(300, 300)))
    assert small.json()["error"]["code"] == "invalid_image"

def test_uploads_cannot_claim_to_be_synthetic_demo_records(env):
    """Otherwise a real record could opt out of the statistical comparison."""
    response = env.submit(actor("observer"), capture_source="synthetic_anomaly_demo")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"

def test_size_limit_is_enforced(env, monkeypatch):
    monkeypatch.setenv("EVIDENCE_MAX_BYTES", "100000")
    get_settings.cache_clear()
    try:
        response = env.submit(actor("observer"), make_sheet_image(1) + b"\x00" * 150_000)
    finally:
        monkeypatch.delenv("EVIDENCE_MAX_BYTES")
        get_settings.cache_clear()
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"

def test_unknown_election_or_polling_unit_is_rejected(env):
    observer = actor("observer")
    response = env.client.post(
        "/api/v1/evidence",
        headers={**observer.headers, "Idempotency-Key": str(uuid.uuid4())},
        data={"election_id": str(uuid.uuid4()), "polling_unit_id": str(UNIT.id)},
        files={"file": ("a.jpg", make_sheet_image(1), "image/jpeg")},
    )
    assert response.json()["error"]["code"] == "unknown_election"
    response = env.client.post(
        "/api/v1/evidence",
        headers={**observer.headers, "Idempotency-Key": str(uuid.uuid4())},
        data={"election_id": str(ELECTION.id), "polling_unit_id": str(uuid.uuid4())},
        files={"file": ("a.jpg", make_sheet_image(1), "image/jpeg")},
    )
    assert response.json()["error"]["code"] == "unknown_polling_unit"

def test_client_hash_mismatch_is_rejected(env):
    response = env.submit(actor("observer"), headers={"X-Content-SHA256": "0" * 64})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "hash_mismatch"

def test_idempotent_retries_return_the_same_record(env):
    observer = actor("observer")
    key = str(uuid.uuid4())
    first = env.submit(observer, key=key)
    again = env.submit(observer, key=key)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["created"] is False
    assert again.json()["item"]["id"] == first.json()["item"]["id"]
    conflict = env.submit(observer, make_sheet_image(2), key=key)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    listing = env.get(observer, "").json()
    assert listing["total"] == 1

def test_duplicate_abuse_is_limited(env):
    observer = actor("observer")
    first = env.submit(observer, make_sheet_image(1))
    same_file = env.submit(observer, make_sheet_image(1))
    assert same_file.json()["item"]["id"] == first.json()["item"]["id"]
    assert env.submit(observer, make_sheet_image(2)).status_code == 201
    assert env.submit(observer, make_sheet_image(3)).status_code == 201
    over = env.submit(observer, make_sheet_image(4))
    assert over.status_code == 429
    assert over.json()["error"]["code"] == "submission_limit_reached"

def test_submitters_cannot_see_each_others_evidence(env):
    alice, bob = actor("observer"), actor("party_agent")
    submission_id = env.submit(alice).json()["item"]["id"]
    for path in ("", "/image", "/audit", "/extraction", "/integrity"):
        assert env.get(bob, f"/{submission_id}{path}").status_code == 404, path
    assert env.post(bob, f"/{submission_id}/process").status_code == 404
    assert env.get(bob, "").json()["total"] == 0
    assert env.get(alice, f"/{submission_id}/comparisons").status_code == 403
    assert env.get(alice, f"/{submission_id}/anomalies").status_code == 403
    assert env.get(alice, "?queue=review").status_code == 403

    reviewer = actor("reviewer")
    staff_view = env.get(reviewer, f"/{submission_id}").json()
    assert staff_view["submitted_by"] == alice.user_id

def test_auditors_are_read_only(env):
    alice = actor("observer")
    submission_id = env.submitted(alice)
    auditor = actor("auditor")
    assert env.get(auditor, f"/{submission_id}/extraction").status_code == 200
    assert env.post(auditor, f"/{submission_id}/validate").status_code == 403
    assert env.post(auditor, f"/{submission_id}/review", {"action": "start"}).status_code == 403
    patch = env.client.patch(
        f"/api/v1/evidence/{submission_id}/extraction",
        headers=auditor.headers,
        json={"corrections": [{"field_key": "party:PA", "value": 1, "reason": "x"}]},
    )
    assert patch.status_code == 403

def test_clients_cannot_set_status(env):
    alice = actor("observer")
    submission_id = env.submit(alice).json()["item"]["id"]
    sneaky = env.client.patch(
        f"/api/v1/evidence/{submission_id}/extraction",
        headers=alice.headers,
        json={"status": "verified", "corrections": []},
    )
    assert sneaky.status_code == 422
    assert env.status(alice, submission_id) == "received"

def test_image_is_served_privately_with_hash_verification(env):
    alice = actor("observer")
    data = make_sheet_image(8)
    submission_id = env.submit(alice, data).json()["item"]["id"]
    response = env.get(alice, f"/{submission_id}/image")
    assert response.status_code == 200
    assert response.content == data
    assert response.headers["x-content-sha256"] == sha256_bytes(data)
    assert "no-store" in response.headers["cache-control"]

    stored = next(env.storage_root.rglob("*.jpg"))
    stored.write_bytes(data + b"tampered")
    tampered = env.get(alice, f"/{submission_id}/image")
    assert tampered.status_code == 409
    assert tampered.json()["error"]["code"] == "evidence_integrity_failure"
    integrity = env.get(alice, f"/{submission_id}/integrity").json()
    assert integrity["original_verified"] is False
    audit = env.get(alice, f"/{submission_id}/audit").json()
    assert "evidence.integrity_failed" in [e["action"] for e in audit["events"]]

def test_processing_refuses_tampered_originals(env):
    alice = actor("observer")
    submission_id = env.submit(alice).json()["item"]["id"]
    next(env.storage_root.rglob("*.jpg")).write_bytes(b"\xff\xd8\xff replaced")
    response = env.post(alice, f"/{submission_id}/process")
    assert response.status_code == 409
    assert env.status(alice, submission_id) == "received"

def test_ocr_extraction_stores_fields_with_confidence_and_derivative(env):
    alice = actor("observer")
    submission_id = env.submitted(alice, overrides={"90": 0.42})
    extraction = env.get(alice, f"/{submission_id}/extraction").json()
    fields = {f["field_key"]: f for f in extraction["fields"]}
    assert extraction["status"] == "completed"
    assert fields["party:PA"]["value"] == 120
    assert fields["party:PA"]["confidence"] == pytest.approx(0.96)
    assert fields["party:PB"]["requires_review"] is True
    assert "party:PB" in extraction["attention_fields"]
    assert fields["party:PA"]["bbox"]["width"] > 0
    assert env.status(alice, submission_id) == "extracted"

    detail = env.get(alice, f"/{submission_id}").json()
    kinds = sorted(i["kind"] for i in detail["images"])
    assert kinds == ["original", "processed"]
    processed = next(i for i in detail["images"] if i["kind"] == "processed")
    assert processed["sha256"] != detail["original_sha256"]
    steps = {s["step"] for s in processed["processing_steps"]}
    assert {
        "exif_orientation",
        "text_orientation",
        "document_boundary",
        "contrast_enhancement",
        "noise_reduction",
    } <= steps

def test_without_ocr_every_field_needs_manual_entry(env):
    env.ocr.available = False
    alice = actor("observer")
    submission_id = env.submit(alice).json()["item"]["id"]
    extraction = env.post(alice, f"/{submission_id}/process").json()
    assert extraction["status"] == "ocr_unavailable"
    assert all(f["requires_review"] for f in extraction["fields"])
    assert all(f["value"] is None for f in extraction["fields"])
    assert "manually" in extraction["error"]

def test_engine_failure_falls_back_to_manual_entry(env):
    env.ocr.fail = True
    alice = actor("observer")
    submission_id = env.submit(alice).json()["item"]["id"]
    extraction = env.post(alice, f"/{submission_id}/process").json()
    assert extraction["status"] == "failed"
    assert env.status(alice, submission_id) == "extracted"

def test_corrections_are_versioned_and_never_overwrite_ocr(env):
    alice = actor("observer")
    submission_id = env.submitted(alice, overrides={"90": 0.42})
    no_reason = env.client.patch(
        f"/api/v1/evidence/{submission_id}/extraction",
        headers=alice.headers,
        json={"corrections": [{"field_key": "party:PB", "value": 95}]},
    )
    assert no_reason.json()["error"]["code"] == "reason_required"
    response = env.client.patch(
        f"/api/v1/evidence/{submission_id}/extraction",
        headers=alice.headers,
        json={
            "corrections": [
                {
                    "field_key": "party:PB",
                    "value": 95,
                    "reason": "Sheet shows 95 on close inspection",
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    field = next(f for f in response.json()["fields"] if f["field_key"] == "party:PB")
    assert field["value"] == 95 and field["version"] == 2 and field["origin"] == "human"
    assert field["ocr_value"] == 90
    assert [h["value"] for h in field["history"]] == [90, 95]
    assert field["requires_review"] is False

    invalid = env.client.patch(
        f"/api/v1/evidence/{submission_id}/extraction",
        headers=alice.headers,
        json={"corrections": [{"field_key": "party:PB", "value": -1, "reason": "x"}]},
    )
    assert invalid.json()["error"]["code"] == "invalid_value"
    unknown = env.client.patch(
        f"/api/v1/evidence/{submission_id}/extraction",
        headers=alice.headers,
        json={"corrections": [{"field_key": "party:ZZ", "value": 1, "reason": "x"}]},
    )
    assert unknown.json()["error"]["code"] == "unknown_field"
    audit = env.get(alice, f"/{submission_id}/audit").json()
    assert "extraction.corrected" in [e["action"] for e in audit["events"]]

def test_arithmetic_failure_flags_for_review(env):
    alice = actor("observer")
    lines = sheet_lines(UNIT.code, cast=400, accredited=300)
    submission_id = env.submitted(alice, lines=lines)
    validation = env.post(alice, f"/{submission_id}/validate")
    assert validation.status_code == 200, validation.text
    body = validation.json()
    assert body["passed"] is False
    assert "cast_equals_valid_plus_rejected" in body["report"]["failed"]
    assert "cast_not_above_accredited" in body["report"]["failed"]
    assert body["is_current"] is True
    assert env.status(alice, submission_id) == "flagged_for_review"

def test_clean_single_submission_is_cross_checked_but_not_verified(env):
    alice = actor("observer")
    submission_id = env.submitted(alice)
    body = env.post(alice, f"/{submission_id}/validate").json()
    assert body["passed"] is True
    assert len(body["result_hash"]) == 64
    assert body["result_hash"] != env.get(alice, f"/{submission_id}").json()["original_sha256"]
    assert env.status(alice, submission_id) == "cross_checked"
    reviewer = actor("reviewer")
    assert (
        env.get(reviewer, f"/{submission_id}/comparisons").json()[0]["report"]["recommendation"][
            "code"
        ]
        == "no_comparison"
    )

def test_low_confidence_values_are_never_silently_accepted(env):
    alice = actor("observer")
    submission_id = env.submitted(alice, overrides={"120": 0.3})
    env.post(alice, f"/{submission_id}/validate")
    assert env.status(alice, submission_id) == "flagged_for_review"
    reviewer = actor("reviewer")
    alerts = env.get(reviewer, f"/{submission_id}/anomalies").json()["alerts"]
    uncertainty = next(a for a in alerts if a["category"] == "ocr_uncertainty")
    assert uncertainty["headline"] == "Anomaly detected. Human review required."
    assert "party:PA" in uncertainty["fields"]

    env.post(reviewer, f"/{submission_id}/review", {"action": "start"})
    blocked = env.post(
        reviewer, f"/{submission_id}/review", {"action": "approve", "notes": "looks fine"}
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "unresolved_fields"

def test_conflicting_submissions_are_compared_field_by_field(env):
    a, b, c = actor("observer"), actor("party_agent"), actor("observer")
    first = env.submitted(a, seed=11)
    env.post(a, f"/{first}/validate")
    second = env.submitted(b, seed=12)
    env.post(b, f"/{second}/validate")
    lines = sheet_lines(
        UNIT.code, parties={"PA": 170, "PB": 90, "PC": 50, "PD": 20}, accredited=400
    )
    third = env.submitted(c, seed=13, lines=lines)
    env.post(c, f"/{third}/validate")

    reviewer = actor("reviewer")
    comparison = env.get(reviewer, f"/{third}/comparisons").json()[0]
    assert comparison["has_conflicts"] is True
    report = comparison["report"]
    assert report["submission_count"] == 3
    pa = next(f for f in report["fields"] if f["field_key"] == "party:PA")
    assert pa["most_common_value"] == "120"
    assert pa["differing_submissions"] == [third]
    assert "party:PB" in report["matching_fields"]
    assert "fraud" not in str(report).lower()
    assert env.status(c, third) == "flagged_for_review"

    alerts = env.get(reviewer, f"/{third}/anomalies").json()
    categories = {a["category"] for a in alerts["alerts"]}
    assert "submission_discrepancy" in categories
    assert "does not determine fraud" in alerts["disclaimer"]
    assert alerts["statistical_analysis"]["status"] == "insufficient_data"

def test_near_duplicate_photos_are_flagged(env):
    a, b = actor("observer"), actor("party_agent")
    original = make_sheet_image(21)
    first = env.submit(a, original).json()["item"]["id"]
    env.ocr.tokens = sheet_tokens(sheet_lines(UNIT.code))
    env.post(a, f"/{first}/process")
    env.post(a, f"/{first}/validate")
    second = env.submit(b, reencode(original, 60)).json()["item"]["id"]
    env.post(b, f"/{second}/process")
    env.post(b, f"/{second}/validate")
    reviewer = actor("reviewer")
    report = env.get(reviewer, f"/{second}/comparisons").json()[0]["report"]
    assert any(d["type"] == "near_duplicate_image" for d in report["duplicates"])
    assert report["recommendation"]["code"] == "review_dependence"
    categories = {a["category"] for a in env.get(reviewer, f"/{second}/anomalies").json()["alerts"]}
    assert "duplicate_evidence" in categories

def ready_for_review(env) -> tuple[str, object]:
    alice = actor("observer")
    submission_id = env.submitted(alice)
    env.post(alice, f"/{submission_id}/validate")
    assert env.status(alice, submission_id) == "cross_checked"
    return submission_id, alice

def test_submitters_cannot_review_and_reviewers_cannot_review_their_own(env):
    submission_id, alice = ready_for_review(env)
    assert env.post(alice, f"/{submission_id}/review", {"action": "start"}).status_code == 403

    admin = actor("election_admin")
    own = env.submitted(admin, seed=3, unit=OTHER_UNIT)
    env.post(admin, f"/{own}/validate")
    response = env.post(admin, f"/{own}/review", {"action": "start"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "conflict_of_interest"

def test_verification_needs_two_independent_reviewer_approvals(env):
    submission_id, alice = ready_for_review(env)
    first, second = actor("reviewer"), actor("reviewer")
    assert env.post(first, f"/{submission_id}/review", {"action": "approve"}).status_code == 409
    env.post(first, f"/{submission_id}/review", {"action": "start"})
    outcome = env.post(first, f"/{submission_id}/review", {"action": "approve", "notes": "ok"})
    assert outcome.status_code == 200, outcome.text
    assert outcome.json()["status"] == "reviewed"
    assert outcome.json()["approvals"] == 1
    again = env.post(first, f"/{submission_id}/review", {"action": "approve", "notes": "ok"})
    assert again.json()["error"]["code"] == "already_approved"

    final = env.post(second, f"/{submission_id}/review", {"action": "approve", "notes": "ok"})
    assert final.json()["status"] == "verified"
    assert final.json()["approvals"] == 2

    # Verified records are frozen.
    patch = env.client.patch(
        f"/api/v1/evidence/{submission_id}/extraction",
        headers=second.headers,
        json={"corrections": [{"field_key": "party:PA", "value": 1, "reason": "x"}]},
    )
    assert patch.status_code == 409
    audit = env.get(second, f"/{submission_id}/audit").json()
    assert audit["chain_valid"] is True
    transitions = [
        e["details"].get("to") for e in audit["events"] if e["action"] == "status.changed"
    ]
    assert transitions[-2:] == ["reviewed", "verified"]

CONFLICTING_LINES = sheet_lines(
    UNIT.code, parties={"PA": 170, "PB": 90, "PC": 50, "PD": 20}, accredited=400
)

def test_approval_uses_current_conflicts_not_the_stale_stored_comparison(env):
    """The first upload was compared when it was alone. A later, conflicting upload for
    the same polling unit must still require explanatory notes before approving it."""
    a, b = actor("observer"), actor("party_agent")
    first = env.submitted(a, seed=31)
    env.post(a, f"/{first}/validate")
    assert env.status(a, first) == "cross_checked"
    second = env.submitted(b, seed=32, lines=CONFLICTING_LINES)
    env.post(b, f"/{second}/validate")

    reviewer, other_reviewer = actor("reviewer"), actor("reviewer")
    stored = env.get(reviewer, f"/{first}/comparisons").json()
    assert [c["has_conflicts"] for c in stored] == [False], "precondition: stored data is stale"
    assert env.status(a, first) == "cross_checked"

    env.post(reviewer, f"/{first}/review", {"action": "start"})
    blocked = env.post(reviewer, f"/{first}/review", {"action": "approve"})
    assert blocked.status_code == 422, blocked.text
    assert blocked.json()["error"]["code"] == "notes_required"
    assert "party:PA" in blocked.json()["error"]["details"]["conflicting_fields"]
    assert env.status(reviewer, first) == "under_human_review"
    whitespace = env.post(reviewer, f"/{first}/review", {"action": "approve", "notes": "   "})
    assert whitespace.json()["error"]["code"] == "notes_required"

    notes = "Compared both images. Sheet one matches the printed totals."
    approved = env.post(reviewer, f"/{first}/review", {"action": "approve", "notes": notes})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "reviewed"

    # The two-person rule still applies, and the second reviewer meets the same notes rule.
    missing = env.post(other_reviewer, f"/{first}/review", {"action": "approve"})
    assert missing.json()["error"]["code"] == "notes_required"
    again = env.post(reviewer, f"/{first}/review", {"action": "approve", "notes": notes})
    assert again.json()["error"]["code"] == "already_approved"
    final = env.post(other_reviewer, f"/{first}/review", {"action": "approve", "notes": notes})
    assert final.json()["status"] == "verified"
    assert final.json()["approvals"] == 2

    audit = env.get(reviewer, f"/{first}/audit").json()
    assert audit["chain_valid"] is True
    recorded = [e["details"] for e in audit["events"] if e["action"] == "review.recorded"]
    approvals = [d for d in recorded if d["decision"] == "approved"]
    assert len(approvals) == 2
    assert all("party:PA" in d["conflicting_fields"] for d in approvals)
    assert all(d["has_notes"] for d in approvals)

def test_conflict_notes_are_not_needed_once_the_conflicting_upload_is_rejected(env):
    a, b = actor("observer"), actor("party_agent")
    first = env.submitted(a, seed=33)
    env.post(a, f"/{first}/validate")
    second = env.submitted(b, seed=34, lines=CONFLICTING_LINES)
    env.post(b, f"/{second}/validate")
    reviewer, other_reviewer = actor("reviewer"), actor("reviewer")

    env.post(reviewer, f"/{second}/review", {"action": "start"})
    rejected = env.post(
        reviewer, f"/{second}/review", {"action": "reject", "notes": "Photo is of another sheet"}
    )
    assert rejected.json()["status"] == "rejected"

    env.post(reviewer, f"/{first}/review", {"action": "start"})
    approved = env.post(reviewer, f"/{first}/review", {"action": "approve"})
    assert approved.status_code == 200, approved.text
    final = env.post(other_reviewer, f"/{first}/review", {"action": "approve"})
    assert final.json()["status"] == "verified"
    audit = env.get(reviewer, f"/{first}/audit").json()
    recorded = [e["details"] for e in audit["events"] if e["action"] == "review.recorded"]
    assert all(d["conflicting_fields"] == [] for d in recorded if d["decision"] == "approved")

def test_corrections_after_approval_require_fresh_validation(env):
    submission_id, _ = ready_for_review(env)
    reviewer = actor("reviewer")
    env.post(reviewer, f"/{submission_id}/review", {"action": "start"})
    env.client.patch(
        f"/api/v1/evidence/{submission_id}/extraction",
        headers=reviewer.headers,
        json={
            "corrections": [
                {"field_key": "registered_voters", "value": 801, "reason": "re-read register count"}
            ]
        },
    )
    assert env.status(reviewer, submission_id) == "extracted"
    integrity = env.get(reviewer, f"/{submission_id}/integrity").json()
    assert integrity["result_hash_matches_validation"] is False
    assert integrity["original_verified"] is True
    assert integrity["audit_chain_valid"] is True

def test_reject_and_request_correction_require_notes(env):
    submission_id, _ = ready_for_review(env)
    reviewer = actor("reviewer")
    env.post(reviewer, f"/{submission_id}/review", {"action": "start"})
    assert (
        env.post(reviewer, f"/{submission_id}/review", {"action": "reject"}).json()["error"]["code"]
        == "notes_required"
    )
    corrected = env.post(
        reviewer,
        f"/{submission_id}/review",
        {"action": "request_correction", "notes": "Blurred party rows"},
    )
    assert corrected.json()["status"] == "extracted"
    env.post(reviewer, f"/{submission_id}/validate")
    env.post(reviewer, f"/{submission_id}/review", {"action": "start"})
    rejected = env.post(
        reviewer,
        f"/{submission_id}/review",
        {"action": "reject", "notes": "Photo is of a different sheet"},
    )
    assert rejected.json()["status"] == "rejected"
    assert env.post(reviewer, f"/{submission_id}/process").status_code == 409

def test_review_queue_lists_records_awaiting_humans(env):
    submission_id, _ = ready_for_review(env)
    reviewer = actor("reviewer")
    queue = env.get(reviewer, "?queue=review").json()
    assert [item["id"] for item in queue["items"]] == [submission_id]

def test_history_rows_are_append_only_in_the_store(env):
    _, _ = ready_for_review(env)
    with env.factory() as db:
        image = db.query(EvidenceImage).first()
        image.storage_path = "elsewhere"
        with pytest.raises(Exception, match="append-only"):
            db.commit()
