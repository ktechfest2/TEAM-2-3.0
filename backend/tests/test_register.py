import random
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.analytics.demo_seed import OBSERVER, DemoPipeline, demo_values
from app.api.v1 import auth as auth_api
from app.auth import create_admin
from app.core.config import get_settings
from app.directory import import_csv
from app.directory.repository import PollingUnitQuery, get_directory
from app.evidence.db import evidence_session_factory
from app.evidence.storage import LocalStorage
from app.main import create_app

ADMIN_EMAIL = "admin@verivote.ng"
ADMIN_PASSWORD = "Correct-Horse-42"

# TEST DATA. Invented names and codes in the INEC code format; not real polling units.
REGISTER = b"""State,LGA,Ward,PU Code,PU Name,Address,Latitude,Longitude,Registered Voters
Test State,Alpha LGA,Ward One,99-01-01-001,Test Primary School I,Beside the market,9.05,7.49,"1,204"
Test State,Alpha LGA,Ward One,99-01-01-002,Test Primary School II,,9.06,7.50,850
Test State,Beta LGA,Ward Two,99-02-01-001,Test Town Hall,Main road,,,
"""

@pytest.fixture()
def api(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DEV_DATABASE_PATH", str(tmp_path / "register.sqlite3"))
    monkeypatch.setenv("DIRECTORY_SOURCE", "database")
    get_settings.cache_clear()
    monkeypatch.setenv("VERIVOTE_ADMIN_PASSWORD", ADMIN_PASSWORD)
    create_admin.main(["--email", ADMIN_EMAIL, "--name", "First Admin"])
    auth_api._sign_in_limiter._hits.clear()
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client
    get_settings.cache_clear()

def headers(api: TestClient) -> dict[str, str]:
    response = api.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

def upload(api: TestClient, auth: dict[str, str], content: bytes, dry_run: bool = False):
    return api.post(
        "/api/v1/admin/register/import",
        headers=auth,
        files={"file": ("register.csv", content, "text/csv")},
        data={"source_name": "Test register", "dry_run": str(dry_run).lower()},
    )

def test_empty_database_directory_is_honest(api):
    states = api.get("/api/v1/locations/states")
    assert states.status_code == 200
    assert states.json()["items"] == []
    assert states.json()["data_source"]["label"] == "Imported register"
    assert api.get("/api/v1/elections").json()["items"] == []
    assert api.get("/api/v1/polling-units").json()["total"] == 0

def test_import_validates_then_applies_and_is_searchable(api):
    auth = headers(api)
    dry = upload(api, auth, REGISTER, dry_run=True).json()
    assert dry["applied"] is False and dry["units_created"] == 3
    assert api.get("/api/v1/polling-units").json()["total"] == 0

    applied = upload(api, auth, REGISTER).json()
    assert applied["applied"] is True
    assert (applied["states_created"], applied["lgas_created"], applied["wards_created"]) == (
        1,
        2,
        2,
    )
    assert applied["units_created"] == 3

    found = api.get("/api/v1/polling-units", params={"q": "primary"}).json()
    assert found["total"] == 2
    unit = found["items"][0]
    assert unit["code"] == "99-01-01-001"
    assert unit["coordinates"]["precision"] == "source_reported"
    assert unit["source_name"] == "Test register"
    assert api.get(f"/api/v1/polling-units/{unit['id']}").status_code == 200
    assert api.get("/api/v1/polling-units", params={"code": "99-02"}).json()["total"] == 1

    state = api.get("/api/v1/locations/states").json()["items"][0]
    lgas = api.get("/api/v1/locations/lgas", params={"state_id": state["id"]}).json()["items"]
    assert [lga["name"] for lga in lgas] == ["Alpha LGA", "Beta LGA"]

    again = upload(api, auth, REGISTER.replace(b"Test Town Hall", b"Test Civic Hall")).json()
    assert (again["units_created"], again["units_updated"], again["units_unchanged"]) == (0, 1, 2)
    same = api.get("/api/v1/polling-units", params={"code": "99-02"}).json()["items"][0]
    assert same["name"] == "Test Civic Hall"

    summary = api.get("/api/v1/admin/register", headers=auth).json()
    assert summary["polling_units"] == 3 and summary["with_coordinates"] == 2
    assert len(summary["imports"]) == 2 and summary["imports"][0]["actor_email"] == ADMIN_EMAIL

def test_one_bad_row_rejects_the_whole_file(api):
    auth = headers(api)
    bad = REGISTER + b"Test State,Alpha LGA,Ward One,99-01-01-001,Duplicate,,95,7,abc\n"
    report = upload(api, auth, bad).json()
    assert report["applied"] is False
    assert report["error_count"] == 1
    message = report["errors"][0]["message"]
    assert report["errors"][0]["row"] == 5
    assert "already appears on row 2" in message and "latitude" in message
    assert api.get("/api/v1/polling-units").json()["total"] == 0

    missing = upload(api, auth, b"State,Ward\nX,Y\n").json()
    assert "Missing required column" in missing["errors"][0]["message"]

def test_register_management_requires_an_election_admin(api):
    assert upload(api, {}, REGISTER).status_code == 401
    assert api.get("/api/v1/admin/register").status_code == 401

def test_elections_are_created_audited_and_served(api):
    auth = headers(api)
    templates = api.get("/api/v1/admin/election-templates", headers=auth).json()
    payload = {
        "name": "Test Governorship Election",
        "election_label": "governorship",
        "election_date": "2027-03-11",
        "template_id": templates[0]["id"],
        "parties": [{"code": "AAA", "name": "Test Party A"}, {"code": "BBB", "name": "B"}],
    }
    created = api.post("/api/v1/admin/elections", headers=auth, json=payload)
    assert created.status_code == 201, created.text
    election = created.json()["election"]
    assert election["election_label"] == "GOVERNORSHIP" and election["is_demo"] is False

    public = api.get("/api/v1/elections").json()["items"]
    assert [e["id"] for e in public] == [election["id"]]

    duplicate = {**payload, "parties": [{"code": "AAA", "name": "x"}, {"code": "AAA", "name": "y"}]}
    assert api.post("/api/v1/admin/elections", headers=auth, json=duplicate).status_code == 422
    unknown = {**payload, "template_id": "nope"}
    assert api.post("/api/v1/admin/elections", headers=auth, json=unknown).status_code == 422

    patched = api.patch(
        f"/api/v1/admin/elections/{election['id']}", headers=auth, json={"status": "active"}
    )
    assert patched.json()["status"] == "active"

    events = api.get(
        "/api/v1/admin/audit-events", headers=auth, params={"entity_type": "election"}
    ).json()
    assert {e["action"] for e in events["items"]} == {"election.created", "election.updated"}

def test_updates_publish_to_the_database(api):
    auth = headers(api)
    update = {
        "title": "Test notice for voters",
        "description": "TEST DATA. Accreditation starts at 08:30 in every test ward.",
        "category": "general_information",
        "source_name": "Test desk",
        "verification_status": "reported_unverified",
    }
    created = api.post("/api/v1/admin/updates", headers=auth, json=update)
    assert created.status_code == 201, created.text
    listed = api.get("/api/v1/updates").json()
    assert listed["total"] == 1 and listed["items"][0]["is_demo"] is False

def test_imported_register_carries_evidence_results_and_ussd(api, tmp_path, monkeypatch):
    auth = headers(api)
    assert upload(api, auth, REGISTER).json()["applied"] is True
    election = api.post(
        "/api/v1/admin/elections",
        headers=auth,
        json={
            "name": "Test Governorship Election",
            "election_label": "GOVERNORSHIP",
            "election_date": "2027-03-11",
            "template_id": api.get("/api/v1/admin/election-templates", headers=auth).json()[0][
                "id"
            ],
            "parties": [{"code": "AAA", "name": "Test Party A"}, {"code": "BBB", "name": "B"}],
            "status": "active",
        },
    ).json()["election"]

    directory = get_directory()
    configured = directory.get_election(uuid.UUID(election["id"]))
    assert configured is not None
    unit = directory.search_polling_units(PollingUnitQuery(code="99-01-01-001"), 1, 1).items[0]
    storage = LocalStorage(str(tmp_path / "evidence"), "evidence")
    with evidence_session_factory()() as db:
        pipe = DemoPipeline(db, storage, get_settings(), directory, configured)
        values = demo_values(unit, configured, random.Random(1))
        pipe.verify(pipe.accepted(unit.id, OBSERVER, values, 1))

    national = api.get("/api/v1/analytics/national", params={"election_id": election["id"]})
    assert national.status_code == 200, national.text
    assert national.json()["election"]["is_demo"] is False

    session = api.post("/api/v1/ussd/sessions", json={"phone_number": "08030000000"}).json()
    api.post(f"/api/v1/ussd/sessions/{session['session_id']}/input", json={"input": "1"})
    reply = api.post(
        f"/api/v1/ussd/sessions/{session['session_id']}/input", json={"input": "99-01-01-001"}
    ).json()["text"]
    assert "99-01-01-001" in reply and "Sample data" not in reply

def test_command_line_import(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEV_DATABASE_PATH", str(tmp_path / "cli.sqlite3"))
    get_settings.cache_clear()
    path = tmp_path / "register.csv"
    path.write_bytes(REGISTER)
    try:
        assert import_csv.main([str(path), "--source", "Test register"]) == 0
        assert "3 polling units created" in capsys.readouterr().out
        path.write_bytes(b"State,LGA,Ward,PU Code,PU Name\nA,B,C,BAD CODE!,X\n")
        assert import_csv.main([str(path), "--source", "Test register"]) == 1
    finally:
        get_settings.cache_clear()
