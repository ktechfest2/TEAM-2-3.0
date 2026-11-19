import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import get_settings
from app.db.enums import NoticeVerificationStatus, PollingUnitStatus
from app.directory.demo_data import build_demo_dataset
from app.main import create_app
from app.schemas.polling_units import OfficialNotice, PollingUnitDetail
from tests.helpers import make_token

DATA = build_demo_dataset()

def _state(name: str):
    return next(s for s in DATA.states if s.name == name)

def test_states_are_labelled_as_demo(client):
    body = client.get("/api/v1/locations/states").json()
    assert {s["name"] for s in body["items"]} == {"Federal Capital Territory", "Kano", "Lagos"}
    assert body["data_source"]["kind"] == "demo"
    assert "not INEC" in body["data_source"]["description"]
    assert body["generated_at"]

def test_cascading_locations(client):
    state = _state("Lagos")
    lgas = client.get("/api/v1/locations/lgas", params={"state_id": str(state.id)}).json()["items"]
    assert [lga["name"] for lga in lgas] == ["Eti-Osa", "Ikeja"]
    assert all(lga["state_id"] == str(state.id) for lga in lgas)

    wards = client.get("/api/v1/locations/wards", params={"lga_id": lgas[0]["id"]}).json()["items"]
    assert [w["name"] for w in wards] == ["Ward A", "Ward B"]

    units = client.get("/api/v1/polling-units", params={"ward_id": wards[0]["id"]}).json()
    assert units["total"] == 3
    assert all(u["ward"]["id"] == wards[0]["id"] for u in units["items"])

def test_lgas_require_a_valid_state_id(client):
    assert client.get("/api/v1/locations/lgas").status_code == 422
    response = client.get("/api/v1/locations/lgas", params={"state_id": "lagos"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"

def test_unknown_parent_returns_empty_list(client):
    response = client.get("/api/v1/locations/wards", params={"lga_id": str(uuid.uuid4())})
    assert response.status_code == 200
    assert response.json()["items"] == []

def test_search_by_name_and_code(client):
    by_name = client.get("/api/v1/polling-units", params={"q": "unit a01"}).json()
    assert by_name["total"] == 6
    assert all("A01" in u["name"] for u in by_name["items"])

    by_code = client.get("/api/v1/polling-units", params={"code": "la1-a"}).json()
    assert by_code["total"] == 4
    assert all(u["code"].startswith("LA1-A") for u in by_code["items"])

def test_search_rejects_invalid_input(client):
    for params in (
        {"q": "a"},
        {"q": "x" * 81},
        {"q": "<script>"},
        {"code": "DROP TABLE;"},
        {"status": "closed"},
        {"page": 0},
        {"page_size": 500},
    ):
        response = client.get("/api/v1/polling-units", params=params)
        assert response.status_code == 422, params
        assert "<script>" not in response.text

def test_search_with_no_matches(client):
    body = client.get("/api/v1/polling-units", params={"q": "no such place"}).json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["total_pages"] == 1

def test_pagination(client):
    first = client.get("/api/v1/polling-units", params={"page_size": 10}).json()
    last = client.get("/api/v1/polling-units", params={"page_size": 10, "page": 5}).json()
    assert first["total"] == 44
    assert first["total_pages"] == 5
    assert len(first["items"]) == 10
    assert len(last["items"]) == 4
    assert {u["id"] for u in first["items"]}.isdisjoint({u["id"] for u in last["items"]})

def test_polling_unit_detail_includes_provenance(client):
    unit = DATA.polling_units[0]
    body = client.get(f"/api/v1/polling-units/{unit.id}").json()
    item = body["item"]
    assert item["code"] == unit.code
    assert item["source_name"].endswith("(not INEC)")
    assert item["source_updated_at"]
    assert item["coordinates"]["precision"] == "demo_approximate"
    assert body["data_source"]["kind"] == "demo"

def test_detail_not_found_and_invalid_id(client):
    assert client.get(f"/api/v1/polling-units/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/v1/polling-units/not-a-uuid").status_code == 422

def test_official_relocation_carries_a_confirmed_sourced_notice(client):
    unit = next(u for u in DATA.polling_units if u.status == PollingUnitStatus.OFFICIALLY_RELOCATED)
    item = client.get(f"/api/v1/polling-units/{unit.id}").json()["item"]
    notice = item["official_notices"][0]
    assert notice["verification_status"] == "officially_confirmed"
    assert notice["source_name"]
    assert notice["reference"]
    assert notice["effective_date"]
    assert notice["received_at"]
    assert "not from INEC" in notice["source_name"]

def test_reported_relocation_is_not_official(client):
    unit = next(u for u in DATA.polling_units if u.status == PollingUnitStatus.RELOCATION_REPORTED)
    item = client.get(f"/api/v1/polling-units/{unit.id}").json()["item"]
    assert item["status"] == "relocation_reported"
    assert item["official_notices"] == []
    assert item["relocation_reports"]["report_count"] == 3
    assert "reporter" not in str(item["relocation_reports"])

def test_official_status_cannot_exist_without_confirmed_source():
    base = DATA.polling_units[0].model_dump()
    unconfirmed = OfficialNotice(
        id=uuid.uuid4(),
        kind="relocation",
        source_name=None,
        received_at=datetime.now(UTC),
        verification_status=NoticeVerificationStatus.OFFICIALLY_CONFIRMED,
    )
    with pytest.raises(ValidationError, match="officially confirmed relocation notice"):
        PollingUnitDetail(
            **{
                **base,
                "status": PollingUnitStatus.OFFICIALLY_RELOCATED,
                "official_notices": [unconfirmed],
            }
        )
    awaiting = unconfirmed.model_copy(
        update={
            "source_name": "Someone",
            "verification_status": NoticeVerificationStatus.AWAITING_CONFIRMATION,
        }
    )
    with pytest.raises(ValidationError):
        PollingUnitDetail(
            **{
                **base,
                "status": PollingUnitStatus.OFFICIALLY_RELOCATED,
                "official_notices": [awaiting],
            }
        )

def test_polling_unit_records_are_read_only(client):
    unit = DATA.polling_units[0]
    for method in ("put", "patch", "delete"):
        response = getattr(client, method)(f"/api/v1/polling-units/{unit.id}")
        assert response.status_code == 405
    assert client.post("/api/v1/polling-units", json={}).status_code == 405

def test_updates_filters(client):
    all_updates = client.get("/api/v1/updates").json()
    assert all_updates["total"] == 6
    dates = [u["published_at"] for u in all_updates["items"]]
    assert dates == sorted(dates, reverse=True)
    assert all(u["is_demo"] for u in all_updates["items"])

    relocation = client.get(
        "/api/v1/updates", params={"category": "polling_unit_relocation"}
    ).json()
    assert relocation["total"] == 2

    unverified = client.get(
        "/api/v1/updates", params={"verification_status": "reported_unverified"}
    ).json()
    assert {u["verification_status"] for u in unverified["items"]} == {"reported_unverified"}

    window = client.get(
        "/api/v1/updates",
        params={"published_from": "2026-11-09T00:00:00Z", "published_to": "2026-11-13T23:59:59Z"},
    ).json()
    assert window["total"] == 2

def test_updates_reject_invalid_ranges_and_categories(client):
    reversed_range = client.get(
        "/api/v1/updates",
        params={"published_from": "2026-11-10T00:00:00Z", "published_to": "2026-11-01T00:00:00Z"},
    )
    assert reversed_range.status_code == 422
    assert client.get("/api/v1/updates", params={"category": "rumour"}).status_code == 422

def test_update_detail(client):
    update = DATA.updates[0]
    assert client.get(f"/api/v1/updates/{update.id}").json()["item"]["title"] == update.title
    assert client.get(f"/api/v1/updates/{uuid.uuid4()}").status_code == 404

VALID_UPDATE = {
    "title": "Polling unit relocated",
    "description": "The polling unit has moved to the new location.",
    "category": "polling_unit_relocation",
    "source_name": "INEC",
    "reference": "INEC/2026/001",
    "verification_status": "officially_confirmed",
}

def test_publishing_requires_an_admin_role(client):
    assert client.post("/api/v1/admin/updates", json=VALID_UPDATE).status_code == 401

    for role in ("observer", "reviewer", "auditor"):
        token = make_token(roles=[role])
        response = client.post(
            "/api/v1/admin/updates",
            json=VALID_UPDATE,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403, role

def test_publishing_without_persistence_is_refused(client):
    token = make_token(roles=["election_admin"])
    response = client.post(
        "/api/v1/admin/updates", json=VALID_UPDATE, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "persistence_unavailable"

def test_official_update_needs_a_traceable_source(client):
    token = make_token(roles=["system_admin"])
    headers = {"Authorization": f"Bearer {token}"}
    no_reference = {k: v for k, v in VALID_UPDATE.items() if k != "reference"}
    assert (
        client.post("/api/v1/admin/updates", json=no_reference, headers=headers).status_code == 422
    )

    insecure = {**VALID_UPDATE, "source_url": "http://example.org/notice"}
    assert client.post("/api/v1/admin/updates", json=insecure, headers=headers).status_code == 422

    client_controlled = {**VALID_UPDATE, "is_demo": False, "published_at": "2026-01-01T00:00:00Z"}
    assert (
        client.post("/api/v1/admin/updates", json=client_controlled, headers=headers).status_code
        == 422
    )

def test_rate_limit(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    get_settings.cache_clear()
    try:
        with TestClient(create_app(), raise_server_exceptions=False) as test_client:
            codes = [test_client.get("/api/v1/locations/states").status_code for _ in range(4)]
            limited = test_client.get(
                "/api/v1/locations/states", headers={"Origin": "http://localhost:5173"}
            )
        assert codes == [200, 200, 200, 429]
        assert limited.json()["error"]["code"] == "rate_limited"
        assert int(limited.headers["retry-after"]) >= 1
        assert limited.headers["access-control-allow-origin"] == "http://localhost:5173"
    finally:
        get_settings.cache_clear()
