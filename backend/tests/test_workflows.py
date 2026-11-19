"""Workflows A to E across the whole API, on the fictional demo register with generated
TEST DATA. Each step uses the same endpoints the web, USSD and SMS clients use."""

from collections.abc import Iterator

import pytest

from app.analytics.registry import registry_for
from tests.evidence_support import actor
from tests.platform_support import CHANNEL_ELECTION, DIRECTORY, Platform, unit_by_code

PU = "FC1-A1"
REVIEWER = actor("reviewer")
ELECTION = {"election_id": str(CHANNEL_ELECTION.id)}

@pytest.fixture()
def platform(tmp_path) -> Iterator[Platform]:
    p = Platform(tmp_path)
    with p.client:
        yield p

def test_voter_information_lookup_and_updates(platform):
    """A: find a polling unit, see its location status, read updates with sources."""
    found = platform.client.get("/api/v1/polling-units", params={"code": PU}).json()
    unit = found["items"][0]
    assert unit["code"] == PU and found["data_source"]["kind"] == "demo"
    detail = platform.client.get(f"/api/v1/polling-units/{unit['id']}").json()["item"]
    assert detail["status"]
    updates = platform.client.get("/api/v1/updates").json()
    assert updates["items"] and all(item["source_name"] for item in updates["items"])
    public = platform.client.get("/api/v1/public/election-updates").json()
    assert [i["id"] for i in public["items"]] == [i["id"] for i in updates["items"]]

def test_results_flow_from_evidence_to_every_channel(platform):
    """B, C and D: verified evidence reaches the dashboard, USSD and SMS identically."""
    platform.seed_results(verified=[PU], reported=[])
    unit = unit_by_code(PU)
    lga_code = registry_for(DIRECTORY, CHANNEL_ELECTION).lgas[unit.lga.id].code

    web = platform.client.get(f"/api/v1/analytics/lgas/{unit.lga.id}", params=ELECTION).json()
    assert web["summary"]["coverage"]["verified_polling_units"] == 1

    sid = platform.client.post("/api/v1/ussd/sessions", json={}).json()["session_id"]
    platform.client.post(f"/api/v1/ussd/sessions/{sid}/input", json={"input": "3"})
    screen = platform.client.post(
        f"/api/v1/ussd/sessions/{sid}/input", json={"input": lga_code}
    ).json()["text"]
    assert "Verified: 1 " in screen

    reply = platform.client.post(
        "/api/v1/sms/incoming", json={"from": "+2348030000077", "text": f"RESULT {PU}"}
    ).json()
    assert "Verified by VoteTrace reviewers" in " ".join(reply["parts"])

def test_incident_from_report_to_published_summary(platform):
    """E: report, triage, review with evidence, publish an approved summary, track."""
    unit = unit_by_code(PU)
    receipt = platform.report(
        category="intimidation",
        description="TEST DATA. Armed men were threatening voters in the queue this morning.",
    ).json()
    assert receipt["reference"].startswith("VV-")
    queue = platform.client.get(
        "/api/v1/incidents", params={"queue": "true", **ELECTION}, headers=REVIEWER.headers
    ).json()
    assert queue["items"][0]["severity"] == "high"

    for status, extra in (
        ("screening", {}),
        ("under_review", {}),
        (
            "verified",
            {
                "evidence_refs": ["evidence:field-call-01"],
                "publish": True,
                "public_summary": "Reviewers verified voter intimidation at a demo polling unit.",
            },
        ),
    ):
        response = platform.client.post(
            f"/api/v1/incidents/{receipt['id']}/review",
            json={"new_status": status, "reason": "Workflow test review step.", **extra},
            headers=REVIEWER.headers,
        )
        assert response.status_code == 200, response.text

    public = platform.client.get("/api/v1/public/incidents", params=ELECTION).json()
    assert public["published"][0]["lga"] == unit.lga.name
    track = platform.client.get(f"/api/v1/incidents/track/{receipt['reference']}").json()
    assert track["band"] == "verified"
