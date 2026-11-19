from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.main import create_app
from tests.helpers import make_token, unsigned_token


def test_me_requires_a_bearer_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"

def test_me_returns_roles_from_app_metadata(client):
    token = make_token(roles=["reviewer"])
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["roles"] == ["reviewer"]
    assert body["email"] == "staff@example.ng"

def test_rejects_expired_wrong_secret_and_unsigned_tokens(client):
    for token in (
        make_token(roles=["system_admin"], expired=True),
        make_token(roles=["system_admin"], secret="another-secret-another-secret-xx"),
        unsigned_token(),
    ):
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"

def test_user_controlled_claims_do_not_grant_roles(client):
    token = make_token(
        roles=["observer"],
        user_metadata_roles=["system_admin"],
        top_level_role="system_admin",
    )
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["roles"] == ["observer"]

    admin = client.get("/api/v1/admin/session", headers={"Authorization": f"Bearer {token}"})
    assert admin.status_code == 403
    assert admin.json()["error"]["code"] == "forbidden"

def test_admin_session_allows_an_admin_role(client):
    token = make_token(roles=["auditor"])
    response = client.get("/api/v1/admin/session", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["roles"] == ["auditor"]

def test_unknown_role_names_are_ignored(client):
    token = make_token(roles=["reviewer", "superuser"])
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.json()["roles"] == ["reviewer"]

def test_auth_fails_closed_when_the_secret_is_unset(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "")
    get_settings.cache_clear()
    application = create_app()
    token = make_token(roles=["system_admin"])
    with TestClient(application, raise_server_exceptions=False) as test_client:
        response = test_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        admin = test_client.get(
            "/api/v1/admin/session", headers={"Authorization": f"Bearer {token}"}
        )
    # A token that cannot be verified is never accepted and never reveals server config.
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert admin.status_code == 401
    get_settings.cache_clear()

def test_malformed_and_forged_tokens_get_401_when_supabase_is_not_configured(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "")
    get_settings.cache_clear()
    candidates = [
        "forged.token.value",
        "not-a-jwt",
        "a.b.c",
        "....",
        unsigned_token(),
        make_token(roles=["system_admin"], expired=True),
        make_token(roles=["system_admin"], secret="another-secret-another-secret-xx"),
        make_token(roles=["system_admin"]),
    ]
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        for token in candidates:
            response = test_client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 401, (token[:20], response.text)
            assert response.json()["error"]["code"] == "unauthorized"
        assert test_client.get("/api/v1/auth/me").status_code == 401
    get_settings.cache_clear()

def test_malformed_tokens_get_401_when_supabase_is_configured(client):
    for token in ("forged.token.value", "not-a-jwt", "a.b.c"):
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401, token
        assert response.json()["error"]["code"] == "unauthorized"

def test_validation_errors_do_not_echo_submitted_secrets():
    application = create_app()

    class Body(BaseModel):
        password: str = Field(min_length=100)

    @application.post("/api/v1/_test/echo")
    def echo(body: Body) -> Body:
        return body

    with TestClient(application, raise_server_exceptions=False) as test_client:
        response = test_client.post(
            "/api/v1/_test/echo",
            json={"password": "hunter2-super-secret"},
        )
    assert response.status_code == 422
    assert "hunter2-super-secret" not in response.text
    assert response.json()["error"]["code"] == "validation_error"

def test_unexpected_errors_hide_connection_details():
    application = create_app()

    @application.get("/api/v1/_test/boom")
    def boom() -> None:
        raise RuntimeError("postgresql://app:super-secret-db-password@db.internal/postgres")

    with TestClient(application, raise_server_exceptions=False) as test_client:
        response = test_client.get("/api/v1/_test/boom")
    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "internal_error",
        "message": "Something went wrong.",
        "request_id": response.json()["error"]["request_id"],
    }
    assert "super-secret-db-password" not in response.text
