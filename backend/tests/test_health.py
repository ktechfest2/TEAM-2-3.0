def test_health_reports_unconfigured_database(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "service": "verivote-api",
        "version": "0.1.0",
        "environment": "test",
        "database": "not_configured",
    }
    assert "secret" not in response.text.lower()
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"

def test_request_id_is_echoed_when_safe(client):
    response = client.get("/api/v1/health", headers={"X-Request-ID": "trace-1234"})
    assert response.headers["x-request-id"] == "trace-1234"

def test_unsafe_request_id_is_replaced(client):
    response = client.get("/api/v1/health", headers={"X-Request-ID": "bad id"})
    assert response.headers["x-request-id"] != "bad id"
    assert len(response.headers["x-request-id"]) >= 8

def test_unknown_route_uses_the_error_envelope(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert response.json()["error"]["request_id"]

def test_cors_allows_only_configured_origins(client):
    allowed = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert allowed.headers.get("access-control-allow-credentials") != "true"

    rejected = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in rejected.headers

    loopback = client.get("/api/v1/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert loopback.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"

def test_mutating_routes_are_admin_or_authenticated_evidence_routes(client):
    mutating = {"post", "put", "patch", "delete"}
    paths = client.app.openapi()["paths"]
    assert "/api/v1/polling-units" in paths
    found = [
        (path, method)
        for path, operations in paths.items()
        for method in operations
        if method in mutating
    ]
    assert ("/api/v1/admin/updates", "post") in found
    # Public intake, each with its own controls: incident reports are rate limited and
    # validated; USSD and SMS accept only signed gateway calls or simulator traffic, and
    # only read electoral data.
    public_intake = {
        ("/api/v1/incidents", "post"),
        ("/api/v1/ussd/sessions", "post"),
        ("/api/v1/ussd/sessions/{session_id}/input", "post"),
        ("/api/v1/ussd/gateway", "post"),
        ("/api/v1/sms/incoming", "post"),
        ("/api/v1/sms/africastalking", "post"),
        # Sign-in is rate limited per address and locks accounts after repeated failures.
        ("/api/v1/auth/login", "post"),
    }
    assert public_intake <= set(found)
    for path, method in found:
        if (path, method) in public_intake:
            continue
        assert path.startswith(
            (
                "/api/v1/admin/",
                "/api/v1/evidence",
                "/api/v1/incidents/{incident_id}/review",
                "/api/v1/auth/password",
            )
        ), path
        url = (
            path.replace("{submission_id}", "00000000-0000-4000-8000-000000000000")
            .replace("{incident_id}", "00000000-0000-4000-8000-000000000000")
            .replace("{user_id}", "00000000-0000-4000-8000-000000000000")
        )
        response = client.request(method.upper(), url)
        assert response.status_code == 401, (path, method)
