"""Incident reporting, triage, review and disclosure. Every report is TEST DATA about the
fictional demo directory."""

import io
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image
from sqlalchemy import select

from app.db.enums import IncidentCategory, IncidentSeverity
from app.db.models import AuditEvent, IncidentAttachment, IncidentReport
from app.evidence.audit import load_chain, verify_chain
from app.incidents import triage, workflow
from app.incidents.service import ENTITY_INCIDENT, normalise_reference
from tests.evidence_support import actor
from tests.platform_support import CHANNEL_ELECTION, Platform, photo, unit_by_code

@pytest.fixture()
def platform(tmp_path) -> Iterator[Platform]:
    p = Platform(tmp_path)
    with p.client:
        yield p

REVIEWER = actor("reviewer")
SECOND_REVIEWER = actor("reviewer")
AUDITOR = actor("auditor")
OBSERVER = actor("observer")

def review(p: Platform, incident_id: str, who=REVIEWER, **payload):
    body = {"reason": "Checked against field notes from the area.", **payload}
    return p.client.post(f"/api/v1/incidents/{incident_id}/review", json=body, headers=who.headers)

def submitted(p: Platform, **kw) -> dict:
    response = p.report(**kw)
    assert response.status_code == 201, response.text
    return response.json()

def test_classification_explains_itself_and_never_overrides_the_reporter():
    result = triage.classify("Men with a gun attacked voters and one was injured.")
    assert result.suggested == IncidentCategory.VIOLENCE
    assert set(result.matches["violence"]) >= {"gun", "attacked", "injured"}
    assert triage.classify("The weather was pleasant today.").suggested is None

def test_severity_rules_escalate_on_harm_and_urgency():
    assert triage.assess_severity(
        IncidentCategory.DELAYED_OFFICIALS, "Officials late."
    ).severity == (IncidentSeverity.LOW)
    grave = triage.assess_severity(IncidentCategory.VIOLENCE, "One person was killed at the unit.")
    assert grave.severity == IncidentSeverity.CRITICAL
    assert any("loss of life" in reason for reason in grave.reasons)
    ongoing = triage.assess_severity(IncidentCategory.INTIMIDATION, "Thugs with a machete, ongoing")
    assert ongoing.severity == IncidentSeverity.HIGH

def test_personal_details_are_masked_and_similarity_is_deterministic():
    text, redacted = triage.clean_text("Call me on 08031234567 or mail me@example.ng now")
    assert redacted and "0803" not in text and "@" not in text
    a = triage.tokens("cash handed to voters at the queue")
    b = triage.tokens("voters at the queue were handed cash")
    assert triage.similarity(a, b) == triage.similarity(b, a) >= 0.5

def test_bands_distinguish_reported_review_corroborated_verified_inconclusive():
    S = workflow.I
    assert workflow.band(S.RECEIVED, 0) == "reported"
    assert workflow.band(S.UNDER_REVIEW, 0) == "under_review"
    assert workflow.band(S.UNDER_REVIEW, 2) == "corroborated"
    assert workflow.band(S.VERIFIED, 0) == "verified"
    assert workflow.band(S.INCONCLUSIVE, 0) == "inconclusive"
    assert workflow.band(S.RESOLVED, 0, S.VERIFIED) == "verified"
    assert workflow.band(S.REJECTED, 0) == "not_substantiated"

def test_anonymous_submission_returns_reference_and_stores_no_identity(platform):
    receipt = submitted(platform)
    assert receipt["created"] is True
    assert receipt["reference"].startswith("VV-") and len(receipt["reference"]) == 17
    assert receipt["status"] == "received" and receipt["band"] == "reported"
    assert "IP address" in receipt["privacy_notice"]
    with platform.factory() as db:
        row = db.get(IncidentReport, uuid.UUID(receipt["id"]))
        assert row.reporter_user_id is None
        assert row.reported_category == row.category == IncidentCategory.VOTE_BUYING
        assert row.triage["classification"]["suggested_category"] == "vote_buying"
        received = load_chain(db, row.id, ENTITY_INCIDENT)
        assert received[0].action == "incident.received" and received[0].actor_id is None
        assert "description" not in received[0].details

def test_report_progress_is_visible_by_reference_only(platform):
    receipt = submitted(platform)
    track = platform.client.get(f"/api/v1/incidents/track/{receipt['reference'].lower()}")
    assert track.status_code == 200
    body = track.json()
    assert body["band"] == "reported" and "description" not in body
    assert platform.client.get("/api/v1/incidents/track/VV-0000-0000-0000").status_code == 404
    assert normalise_reference(" vv-abcd-efgh-ijk0 ") == "VV-ABCD-EFGH-1JK0"

def test_validation_rejects_inconsistent_location_future_time_and_short_text(platform):
    other = unit_by_code("LA1-A1")
    wrong_lga = platform.report(lga_id=str(other.lga.id))
    assert wrong_lga.status_code == 422 and wrong_lga.json()["error"]["code"] == "unknown_lga"
    future = platform.report(occurred_at=(datetime.now(UTC) + timedelta(days=1)).isoformat())
    assert future.json()["error"]["code"] == "invalid_time"
    short = platform.report(description="too short")
    assert short.status_code == 422
    bad_category = platform.report(category="made_up")
    assert bad_category.status_code == 422
    lonely_lat = platform.report(latitude="9.05")
    assert lonely_lat.json()["error"]["code"] == "invalid_coordinates"

def test_polling_unit_alone_fills_in_its_ward(platform):
    receipt = submitted(platform, ward_id=None)
    with platform.factory() as db:
        row = db.scalar(
            select(IncidentReport).where(IncidentReport.reference == receipt["reference"])
        )
        assert row.ward_id == unit_by_code("FC1-A1").ward.id

def test_retries_are_idempotent_and_exact_duplicates_are_refused(platform):
    first = platform.report(key="2b0d7c1e-4d1a-4f0e-9a51-0c6b8f1e2a10")
    retry = platform.report(key="2b0d7c1e-4d1a-4f0e-9a51-0c6b8f1e2a10")
    assert first.status_code == 201 and retry.status_code == 200
    assert retry.json()["reference"] == first.json()["reference"]
    assert retry.json()["created"] is False
    duplicate = platform.report()
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_report"
    with platform.factory() as db:
        assert len(db.scalars(select(IncidentReport)).all()) == 1

def test_similar_reports_are_grouped_and_marked_as_possible_duplicates(platform):
    first = submitted(platform)
    second = submitted(
        platform,
        description=(
            "TEST DATA. Cash and rice were handed out to voters in the queue near the "
            "polling unit entrance this morning."
        ),
    )
    detail = platform.client.get(f"/api/v1/incidents/{second['id']}", headers=REVIEWER.headers)
    body = detail.json()
    assert body["similar_count"] == 1
    assert body["triage"]["similar_reports"][0]["reference"] == first["reference"]
    assert body["possible_duplicate_of"] == first["reference"]
    earlier = platform.client.get(f"/api/v1/incidents/{first['id']}", headers=REVIEWER.headers)
    assert earlier.json()["triage"]["corroborating_reports"] == 1

def test_submissions_are_rate_limited_per_connection(platform, monkeypatch):
    monkeypatch.setenv("INCIDENT_SUBMISSIONS_PER_HOUR", "2")
    from app.core.config import get_settings

    get_settings.cache_clear()
    descriptions = [
        f"TEST DATA report number {i} about a delayed opening at the unit." for i in range(3)
    ]
    codes = [platform.report(description=d).status_code for d in descriptions]
    assert codes == [201, 201, 429]
    get_settings.cache_clear()

def test_photo_is_stored_privately_without_camera_metadata(platform):
    original = photo(with_exif=True)
    with Image.open(io.BytesIO(original)) as probe:
        assert probe.getexif().get(0x0110) == "TestCameraModel"
    receipt = submitted(platform, file=("scene.jpg", original, "image/jpeg"))
    assert receipt["attachment_stored"] is True
    detail = platform.client.get(f"/api/v1/incidents/{receipt['id']}", headers=REVIEWER.headers)
    attachment = detail.json()["attachments"][0]
    image = platform.client.get(
        f"/api/v1/incidents/{receipt['id']}/attachments/{attachment['id']}",
        headers=REVIEWER.headers,
    )
    assert image.status_code == 200 and image.headers["x-content-sha256"] == attachment["sha256"]
    with Image.open(io.BytesIO(image.content)) as stored:
        assert len(stored.getexif()) == 0
    public = platform.client.get(
        f"/api/v1/incidents/{receipt['id']}/attachments/{attachment['id']}"
    )
    assert public.status_code == 401
    with platform.factory() as db:
        assert db.scalar(select(IncidentAttachment)).storage_path.startswith("incidents/")

def test_unsupported_attachments_are_refused(platform):
    fake = platform.report(file=("scene.jpg", b"GIF89a" + b"\x00" * 3000, "image/jpeg"))
    assert fake.status_code == 415
    tiny = platform.report(file=("scene.jpg", photo((80, 80)), "image/jpeg"))
    assert tiny.status_code == 422
    with platform.factory() as db:
        assert db.scalars(select(IncidentReport)).all() == []

def test_reading_reports_needs_an_incident_staff_role(platform):
    receipt = submitted(platform)
    assert platform.client.get("/api/v1/incidents").status_code == 401
    assert platform.client.get("/api/v1/incidents", headers=OBSERVER.headers).status_code == 403
    assert platform.client.get(f"/api/v1/incidents/{receipt['id']}").status_code == 401
    assert (
        platform.client.get("/api/v1/incidents/stats", headers=OBSERVER.headers).status_code == 403
    )
    auditor_view = platform.client.get(
        f"/api/v1/incidents/{receipt['id']}", headers=AUDITOR.headers
    )
    assert auditor_view.status_code == 200
    assert auditor_view.json()["can_review"] is False

def test_only_reviewers_change_status_and_never_on_their_own_report(platform):
    receipt = submitted(platform)
    assert review(platform, receipt["id"], who=AUDITOR, new_status="screening").status_code == 403
    assert review(platform, receipt["id"], who=OBSERVER, new_status="verified").status_code == 403
    no_token = platform.client.post(
        f"/api/v1/incidents/{receipt['id']}/review",
        json={"new_status": "verified", "reason": "Trying to verify my own report."},
    )
    assert no_token.status_code == 401

    reporter = actor("reviewer")
    own = submitted(
        platform,
        headers=reporter.headers,
        description="TEST DATA. A reviewer reported officials arriving three hours late here.",
        category="delayed_officials",
    )
    blocked = review(platform, own["id"], who=reporter, new_status="screening")
    assert blocked.status_code == 403
    assert "you submitted" in blocked.json()["error"]["message"]

def test_protected_reporter_is_hidden_even_from_staff(platform):
    reporter = actor("observer")
    protected = submitted(platform, headers=reporter.headers, protect_identity="true")
    detail = platform.client.get(f"/api/v1/incidents/{protected['id']}", headers=REVIEWER.headers)
    assert detail.json()["reporter_user_id"] is None
    with platform.factory() as db:
        row = db.scalar(select(IncidentReport))
        assert row.identity_protected is True
        assert load_chain(db, row.id, ENTITY_INCIDENT)[0].actor_id is None

    open_reporter = actor("observer")
    linked = submitted(
        platform,
        headers=open_reporter.headers,
        category="accessibility",
        description="TEST DATA. There was no ramp so a wheelchair user could not enter the unit.",
    )
    shown = platform.client.get(f"/api/v1/incidents/{linked['id']}", headers=REVIEWER.headers)
    assert shown.json()["reporter_user_id"] == open_reporter.user_id

def test_status_transitions_follow_the_workflow_and_are_recorded(platform):
    receipt = submitted(platform)
    iid = receipt["id"]
    assert review(platform, iid, new_status="resolved").status_code == 409
    assert review(platform, iid, new_status="screening").status_code == 200
    assert review(platform, iid, new_status="under_review").status_code == 200
    needs_evidence = review(platform, iid, new_status="verified")
    assert needs_evidence.json()["error"]["code"] == "evidence_required"
    verified = review(
        platform,
        iid,
        who=SECOND_REVIEWER,
        new_status="verified",
        evidence_refs=["evidence:demo-photo-1", "update:DEMO-REF-0002"],
        severity="high",
    )
    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert body["status"] == "verified" and body["band"] == "verified"
    assert body["severity"] == "high"
    history = body["reviews"]
    assert [(r["previous_status"], r["new_status"]) for r in history] == [
        ("received", "screening"),
        ("screening", "under_review"),
        ("under_review", "verified"),
    ]
    assert history[-1]["reviewer_id"] == SECOND_REVIEWER.user_id
    assert history[-1]["evidence_refs"] == ["evidence:demo-photo-1", "update:DEMO-REF-0002"]
    assert history[-1]["severity_from"] == "medium" and history[-1]["severity_to"] == "high"
    resolved = review(platform, iid, new_status="resolved")
    assert resolved.json()["band"] == "verified"
    assert resolved.json()["allowed_transitions"] == []

    with platform.factory() as db:
        events = load_chain(db, db.scalar(select(IncidentReport.id)), ENTITY_INCIDENT)
        assert verify_chain(events).valid
        assert [e.action for e in events].count("incident.reviewed") == 4

def test_category_correction_keeps_the_original_report(platform):
    receipt = submitted(platform)
    corrected = review(
        platform, receipt["id"], new_status="screening", category="voting_disruption"
    )
    body = corrected.json()
    assert body["category"] == "voting_disruption"
    assert body["reported_category"] == "vote_buying"
    assert "cash and rice" in body["description"]

def test_no_op_reviews_and_unknown_incidents_are_refused(platform):
    receipt = submitted(platform)
    assert review(platform, receipt["id"], new_status="received").json()["error"]["code"] == (
        "no_change"
    )
    missing = review(platform, "00000000-0000-4000-8000-000000000000", new_status="screening")
    assert missing.status_code == 404

def test_only_verified_incidents_can_be_published_and_only_as_a_summary(platform):
    receipt = submitted(platform)
    iid = receipt["id"]
    early = review(
        platform,
        iid,
        new_status="screening",
        publish=True,
        public_summary="Reviewers are looking into reports of inducements near a polling unit.",
    )
    assert early.json()["error"]["code"] == "not_publishable"
    review(platform, iid, new_status="screening")
    review(platform, iid, new_status="under_review")
    published = review(
        platform,
        iid,
        new_status="verified",
        evidence_refs=["evidence:demo-1"],
        publish=True,
        public_summary=(
            "Reviewers verified reports of inducements offered near a demo polling unit."
        ),
    )
    assert published.status_code == 200 and published.json()["is_public"] is True

    public = platform.client.get(
        "/api/v1/public/incidents", params={"election_id": str(CHANNEL_ELECTION.id)}
    )
    assert public.status_code == 200
    data = public.json()
    assert data["demo_label"]
    assert len(data["published"]) == 1
    item = data["published"][0]
    assert item["summary"].startswith("Reviewers verified")
    serialised = public.text
    for secret in ("cash and rice", receipt["reference"], receipt["id"], "reporter"):
        assert secret not in serialised
    assert {b["key"]: b["count"] for b in data["by_band"]}["verified"] == 1
    track = platform.client.get(f"/api/v1/incidents/track/{receipt['reference']}").json()
    assert track["public_summary"].startswith("Reviewers verified")

def test_dashboard_counts_filters_and_queue(platform):
    lagos = unit_by_code("LA1-A1")
    submitted(platform)
    submitted(
        platform,
        unit_code=lagos.code,
        category="violence",
        description="TEST DATA. A man was killed when thugs attacked the queue at the unit.",
    )
    late = submitted(
        platform,
        unit_code="FC2-A1",
        category="delayed_officials",
        description="TEST DATA. Officials had not arrived by ten in the morning at this unit.",
    )
    review(platform, late["id"], new_status="screening")
    review(platform, late["id"], new_status="unverified")

    stats = platform.client.get("/api/v1/incidents/stats", headers=REVIEWER.headers).json()
    assert stats["total"] == 3
    assert stats["awaiting_review"] == 2 and stats["unverified"] == 1
    assert stats["critical_open"] == 1
    assert {c["key"]: c["count"] for c in stats["by_category"]}["violence"] == 1
    assert {s["name"]: s["count"] for s in stats["by_state"]}["Lagos"] == 1
    assert sum(point["count"] for point in stats["timeline"]) == 3

    lagos_only = platform.client.get(
        "/api/v1/incidents/stats",
        params={"state_id": str(lagos.state.id)},
        headers=REVIEWER.headers,
    ).json()
    assert lagos_only["total"] == 1

    queue = platform.client.get(
        "/api/v1/incidents", params={"queue": "true"}, headers=REVIEWER.headers
    ).json()
    assert [item["severity"] for item in queue["items"]] == ["critical", "medium"]
    assert all("description" not in item for item in queue["items"])
    filtered = platform.client.get(
        "/api/v1/incidents",
        params={"category": "delayed_officials", "status": "unverified"},
        headers=REVIEWER.headers,
    ).json()
    assert filtered["total"] == 1
    bad_range = platform.client.get(
        "/api/v1/incidents",
        params={"occurred_from": "2026-11-20T00:00:00Z", "occurred_to": "2026-11-01T00:00:00Z"},
        headers=REVIEWER.headers,
    )
    assert bad_range.status_code == 422

def test_incident_audit_events_cannot_be_edited(platform):
    submitted(platform)
    with platform.factory() as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.entity_type == ENTITY_INCIDENT))
        event.action = "tampered"
        with pytest.raises(Exception, match="append-only"):
            db.commit()
