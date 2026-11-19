from collections.abc import Iterator

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.v1 import auth as auth_api
from app.auth import create_admin, passwords
from app.core.config import get_settings
from app.main import create_app
from tests.helpers import make_token

ADMIN_EMAIL = "admin@verivote.ng"
ADMIN_PASSWORD = "Correct-Horse-42"

@pytest.fixture()
def api(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DEV_DATABASE_PATH", str(tmp_path / "accounts.sqlite3"))
    monkeypatch.setenv("AUTH_MAX_FAILED_ATTEMPTS", "3")
    get_settings.cache_clear()
    monkeypatch.setenv("VERIVOTE_ADMIN_PASSWORD", ADMIN_PASSWORD)
    create_admin.main(["--email", ADMIN_EMAIL, "--name", "First Admin"])
    auth_api._sign_in_limiter._hits.clear()
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client
    get_settings.cache_clear()

def login(api: TestClient, email: str, password: str):
    return api.post("/api/v1/auth/login", json={"email": email, "password": password})

def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

def admin_headers(api: TestClient) -> dict[str, str]:
    response = login(api, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert response.status_code == 200, response.text
    return bearer(response.json()["access_token"])

def test_password_hashes_verify_and_are_salted():
    first = passwords.hash_password("A-good-password-1")
    second = passwords.hash_password("A-good-password-1")
    assert first != second
    assert passwords.verify_password("A-good-password-1", first)
    assert not passwords.verify_password("A-good-password-2", first)
    assert not passwords.verify_password("anything", "not-a-hash")

def test_weak_passwords_are_refused():
    assert passwords.password_problem("short") is not None
    assert passwords.password_problem("aaaaaaaaaaaa") is not None
    assert passwords.password_problem("chinedu-2027-vote", "chinedu@example.ng") is not None
    assert passwords.password_problem("Correct-Horse-42") is None

def test_admin_signs_in_and_reaches_admin_routes(api):
    response = login(api, ADMIN_EMAIL.upper(), ADMIN_PASSWORD)
    assert response.status_code == 200
    body = response.json()
    assert body["account"]["roles"] == ["system_admin"]
    assert body["account"]["must_change_password"] is False
    assert "scrypt$" not in response.text
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    assert claims["iss"] == "verivote" and claims["app_metadata"]["roles"] == ["system_admin"]

    headers = bearer(body["access_token"])
    me = api.get("/api/v1/auth/me", headers=headers)
    assert me.json()["roles"] == ["system_admin"]
    assert api.get("/api/v1/admin/session", headers=headers).status_code == 200
    assert api.get("/api/v1/admin/users", headers=headers).status_code == 200

def test_wrong_password_and_unknown_email_look_the_same(api):
    wrong = login(api, ADMIN_EMAIL, "Wrong-password-1")
    unknown = login(api, "nobody@verivote.ng", "Wrong-password-1")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]

def test_repeated_failures_lock_the_account(api):
    for _ in range(3):
        assert login(api, ADMIN_EMAIL, "Wrong-password-1").status_code == 401
    locked = login(api, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "account_locked"

def test_new_account_with_temporary_password_must_change_it_first(api):
    headers = admin_headers(api)
    created = api.post(
        "/api/v1/admin/users",
        headers=headers,
        json={"email": "reviewer@verivote.ng", "roles": ["reviewer"]},
    )
    assert created.status_code == 201, created.text
    temporary = created.json()["temporary_password"]
    assert temporary and created.json()["account"]["must_change_password"] is True

    first = login(api, "reviewer@verivote.ng", temporary)
    assert first.status_code == 200
    assert first.json()["account"]["must_change_password"] is True
    limited = bearer(first.json()["access_token"])
    assert api.get("/api/v1/auth/me", headers=limited).json()["must_change_password"] is True
    assert api.get("/api/v1/incidents", headers=limited).status_code == 403

    changed = api.post(
        "/api/v1/auth/password",
        headers=limited,
        json={"current_password": temporary, "new_password": "Review-Desk-2027"},
    )
    assert changed.status_code == 200, changed.text
    fresh = bearer(changed.json()["access_token"])
    assert api.get("/api/v1/auth/me", headers=fresh).json()["roles"] == ["reviewer"]
    assert api.get("/api/v1/incidents", headers=fresh).status_code == 200
    # The token issued before the change no longer works.
    assert api.get("/api/v1/auth/me", headers=limited).status_code == 401

def test_role_changes_and_disabling_apply_to_existing_tokens(api):
    headers = admin_headers(api)
    created = api.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "observer@verivote.ng",
            "roles": ["observer"],
            "password": "Field-Desk-Kano-77",
        },
    ).json()
    user_id = created["account"]["id"]
    token = bearer(login(api, "observer@verivote.ng", "Field-Desk-Kano-77").json()["access_token"])
    assert api.get("/api/v1/auth/me", headers=token).json()["roles"] == ["observer"]

    api.patch(f"/api/v1/admin/users/{user_id}", headers=headers, json={"roles": ["party_agent"]})
    assert api.get("/api/v1/auth/me", headers=token).json()["roles"] == ["party_agent"]

    api.patch(f"/api/v1/admin/users/{user_id}", headers=headers, json={"is_active": False})
    assert api.get("/api/v1/auth/me", headers=token).status_code == 401
    assert login(api, "observer@verivote.ng", "Field-Desk-Kano-77").status_code == 403

def test_password_reset_ends_sessions(api):
    headers = admin_headers(api)
    user_id = api.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "agent@verivote.ng",
            "roles": ["party_agent"],
            "password": "Ward-Count-Desk-901",
        },
    ).json()["account"]["id"]
    token = bearer(login(api, "agent@verivote.ng", "Ward-Count-Desk-901").json()["access_token"])
    reset = api.post(f"/api/v1/admin/users/{user_id}/password-reset", headers=headers)
    assert reset.status_code == 200
    assert api.get("/api/v1/auth/me", headers=token).status_code == 401
    assert login(api, "agent@verivote.ng", "Ward-Count-Desk-901").status_code == 401
    assert login(api, "agent@verivote.ng", reset.json()["temporary_password"]).status_code == 200

def test_only_system_admins_manage_accounts(api):
    headers = admin_headers(api)
    api.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "ea@verivote.ng",
            "roles": ["election_admin"],
            "password": "Election-Admin-55",
        },
    )
    other = bearer(login(api, "ea@verivote.ng", "Election-Admin-55").json()["access_token"])
    assert api.get("/api/v1/admin/users", headers=other).status_code == 403
    denied = api.post(
        "/api/v1/admin/users",
        headers=other,
        json={"email": "x@verivote.ng", "roles": ["system_admin"]},
    )
    assert denied.status_code == 403
    assert api.get("/api/v1/admin/users").status_code == 401

def test_duplicate_emails_and_last_admin_are_protected(api):
    headers = admin_headers(api)
    duplicate = api.post(
        "/api/v1/admin/users",
        headers=headers,
        json={"email": ADMIN_EMAIL.upper(), "roles": ["reviewer"]},
    )
    assert duplicate.status_code == 409
    me = api.get("/api/v1/auth/account", headers=headers).json()
    demote = api.patch(
        f"/api/v1/admin/users/{me['id']}", headers=headers, json={"roles": ["reviewer"]}
    )
    assert demote.status_code == 409
    disable = api.patch(
        f"/api/v1/admin/users/{me['id']}", headers=headers, json={"is_active": False}
    )
    assert disable.status_code == 409

def test_forged_local_tokens_are_rejected(api):
    forged = jwt.encode(
        {
            "iss": "verivote",
            "aud": "authenticated",
            "sub": "00000000-0000-4000-8000-000000000000",
            "ver": 1,
            "exp": 9999999999,
            "app_metadata": {"roles": ["system_admin"]},
        },
        "guessed-secret-guessed-secret-guessed",
        algorithm="HS256",
    )
    assert api.get("/api/v1/auth/me", headers=bearer(forged)).status_code == 401

def test_supabase_tokens_keep_working(api):
    token = make_token(roles=["auditor"])
    assert api.get("/api/v1/admin/session", headers=bearer(token)).status_code == 200

def test_create_admin_restores_a_lost_admin_password(api, monkeypatch):
    monkeypatch.setenv("VERIVOTE_ADMIN_PASSWORD", "Brand-New-Secret-9")
    create_admin.main(["--email", ADMIN_EMAIL])
    assert login(api, ADMIN_EMAIL, ADMIN_PASSWORD).status_code == 401
    assert login(api, ADMIN_EMAIL, "Brand-New-Secret-9").status_code == 200

def test_account_changes_appear_in_the_audit_log_with_intact_chains(api):
    headers = admin_headers(api)
    created = api.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "auditor@verivote.ng",
            "roles": ["auditor"],
            "password": "Ledger-Check-2027",
        },
    ).json()
    page = api.get("/api/v1/admin/audit-events?entity_type=account", headers=headers)
    assert page.status_code == 200
    actions = {item["action"] for item in page.json()["items"]}
    assert {"account.created"} <= actions
    assert "account" in page.json()["entity_types"]
    assert all(
        "password" not in str(item["details"]).replace("temporary_password", "")
        for item in page.json()["items"]
    )

    chain = api.get(
        f"/api/v1/admin/audit-events/chains/account/{created['account']['id']}", headers=headers
    )
    assert (
        chain.status_code == 200 and chain.json()["valid"] is True and chain.json()["events"] == 1
    )

    auditor = bearer(login(api, "auditor@verivote.ng", "Ledger-Check-2027").json()["access_token"])
    assert api.get("/api/v1/admin/audit-events", headers=auditor).status_code == 200
    assert api.get("/api/v1/admin/audit-events").status_code == 401
