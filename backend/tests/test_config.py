import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.core.logging import redact, redact_text
from app.db.session import get_engine

def test_database_url_uses_the_psycopg_driver():
    settings = Settings(database_url="postgres://app:secret@localhost:5432/verivote")
    assert settings.database_url == "postgresql+psycopg://app:secret@localhost:5432/verivote"

def test_blank_database_url_is_unset():
    assert Settings(database_url="  ").database_url is None

def test_wildcard_cors_is_rejected():
    with pytest.raises(ValidationError):
        Settings(cors_origins="*")

def test_short_jwt_secret_is_rejected():
    with pytest.raises(ValidationError):
        Settings(supabase_jwt_secret=SecretStr("too-short"))

def test_production_refuses_to_start_half_configured():
    settings = Settings(
        app_env="production",
        database_url=None,
        supabase_jwt_secret=None,
        cors_origins="",
    )
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        settings.assert_runtime_safe()

def test_settings_repr_hides_secrets():
    settings = Settings(
        supabase_jwt_secret=SecretStr("jwt-secret-value-jwt-secret-value"),
        supabase_service_role_key=SecretStr("service-role-value-service-role"),
    )
    rendered = repr(settings)
    assert "jwt-secret-value-jwt-secret-value" not in rendered
    assert "service-role-value-service-role" not in rendered

def test_redaction_strips_secrets_from_text_and_mappings():
    text = redact_text("Authorization: Bearer abc.def.ghi password=hunter2")
    assert "abc.def.ghi" not in text
    assert "hunter2" not in text

    url = redact_text("failed postgresql://app:super-secret@db.internal/postgres")
    assert "super-secret" not in url

    cleaned = redact({"password": "hunter2", "note": "kept", "nested": [{"api_key": "k"}]})
    assert cleaned == {
        "password": "[redacted]",
        "note": "kept",
        "nested": [{"api_key": "[redacted]"}],
    }

def test_engine_requires_a_configured_database():
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        get_engine()

def test_loopback_twin_is_allowed_only_outside_production():
    dev = Settings(cors_origins="http://localhost:5173", app_env="development")
    assert "http://127.0.0.1:5173" in dev.cors_origin_list
    assert "http://localhost:5173" in dev.cors_origin_list
    prod = Settings(cors_origins="https://app.example.org", app_env="production")
    assert prod.cors_origin_list == ["https://app.example.org"]
