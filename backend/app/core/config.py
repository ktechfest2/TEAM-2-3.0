from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets stay in the environment, never in code."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = "verivote-api"
    app_version: str = "0.1.0"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    cors_origins: str = "http://localhost:5173"

    # "database" serves the register imported by administrators, the elections they
    # configure and the updates they publish. "demo" serves the fictional dataset in
    # app/directory/demo_data.py and is meant for tests and walkthroughs only.
    directory_source: Literal["database", "demo"] = "database"

    # Per-client requests per minute on /api/v1. 0 disables the limiter.
    rate_limit_per_minute: int = Field(default=120, ge=0, le=10_000)
    # Only enable behind a proxy you control that overwrites X-Forwarded-For.
    trust_proxy_headers: bool = False

    # Evidence storage. "local" keeps originals in a private directory and is for
    # development and tests only; production must use the private Supabase bucket.
    evidence_storage: Literal["local", "supabase"] = "local"
    evidence_local_dir: str = "var/evidence"
    evidence_bucket: str = "evidence"
    # Used for evidence records when DATABASE_URL is unset (development and test only).
    dev_database_path: str = "var/dev-evidence.sqlite3"

    evidence_max_bytes: int = Field(default=15 * 1024 * 1024, ge=100_000, le=50 * 1024 * 1024)
    evidence_min_dimension: int = Field(default=500, ge=100)
    evidence_max_dimension: int = Field(default=12_000, le=20_000)
    # Cap on accepted submissions per user, per election and polling unit.
    evidence_max_per_polling_unit: int = Field(default=3, ge=1, le=20)

    ocr_provider: Literal["auto", "tesseract", "rapidocr", "none"] = "auto"
    # Fields below this confidence are flagged for human confirmation.
    ocr_confidence_threshold: float = Field(default=0.85, gt=0, le=1)

    # Distinct reviewer approvals needed before a record can become VERIFIED.
    verification_required_approvals: int = Field(default=2, ge=1, le=5)
    # Reliable (human-reviewed) records needed before statistical analysis runs.
    anomaly_min_samples: int = Field(default=30, ge=10)

    # Incident reports. Limits are per client address, counted in memory only (the
    # address is never stored with a report).
    incident_submissions_per_hour: int = Field(default=10, ge=0, le=1_000)
    incident_attachment_max_bytes: int = Field(
        default=8 * 1024 * 1024, ge=100_000, le=20 * 1024 * 1024
    )
    incident_attachment_min_dimension: int = Field(default=200, ge=50)
    # Reports in the same area and category within this window are compared for similarity.
    incident_similarity_window_hours: int = Field(default=6, ge=1, le=72)

    # USSD and SMS. The simulator accepts unsigned requests and returns replies in the
    # HTTP response; it is on by default outside production. Real gateways must sign
    # callbacks with the matching webhook secret (HMAC-SHA256 of the raw body).
    channel_simulator_enabled: bool | None = None
    ussd_webhook_secret: SecretStr | None = None
    sms_webhook_secret: SecretStr | None = None
    # Key for hashing telephone numbers. Numbers are never stored in clear.
    channel_hash_secret: SecretStr | None = None
    # Election answered by USSD and SMS. Defaults to the latest election in the directory.
    channel_election_id: str | None = None
    # Providers that cannot sign callbacks (Africa's Talking) prove origin with this token
    # in the callback URL: /api/v1/ussd/gateway?token=... and /api/v1/sms/africastalking?token=...
    channel_callback_token: SecretStr | None = None
    # Africa's Talking account for outbound SMS replies. "sandbox" uses the free test
    # environment and its simulator; "live" sends real messages and costs money.
    africastalking_username: str | None = None
    africastalking_api_key: SecretStr | None = None
    africastalking_environment: Literal["sandbox", "live"] = "sandbox"
    # Optional approved sender ID or shortcode for replies.
    africastalking_sender_id: str | None = None
    ussd_session_timeout_seconds: int = Field(default=180, ge=30, le=900)
    sms_messages_per_window: int = Field(default=10, ge=1, le=1_000)
    sms_window_seconds: int = Field(default=600, ge=10, le=86_400)

    # Built-in accounts. Tokens are HS256 with this secret and issuer "verivote". Without
    # it, development generates one under var/ on first use; production requires it.
    auth_jwt_secret: SecretStr | None = None
    auth_token_minutes: int = Field(default=480, ge=5, le=7 * 24 * 60)
    # Failed sign-ins per email and per client address before a temporary lock.
    auth_max_failed_attempts: int = Field(default=5, ge=1, le=100)
    auth_lockout_minutes: int = Field(default=15, ge=1, le=24 * 60)

    database_url: str | None = None
    supabase_url: str | None = None
    supabase_jwt_secret: SecretStr | None = None
    supabase_service_role_key: SecretStr | None = Field(default=None)

    @field_validator("cors_origins")
    @classmethod
    def explicit_origins_only(cls, value: str) -> str:
        origins = [item.strip().rstrip("/") for item in value.split(",") if item.strip()]
        if any(origin == "*" for origin in origins):
            raise ValueError("CORS_ORIGINS must list explicit origins and must not contain '*'")
        return ",".join(origins)

    @field_validator("database_url", mode="before")
    @classmethod
    def normalise_database_url(cls, value: object) -> object:
        if value is None or not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.startswith("postgres://"):
            stripped = "postgresql://" + stripped.removeprefix("postgres://")
        if stripped.startswith("postgresql+psycopg2://"):
            stripped = "postgresql+psycopg://" + stripped.removeprefix("postgresql+psycopg2://")
        elif stripped.startswith("postgresql://"):
            stripped = "postgresql+psycopg://" + stripped.removeprefix("postgresql://")
        return stripped

    @field_validator("supabase_url", mode="before")
    @classmethod
    def blank_url_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator(
        "supabase_jwt_secret",
        "auth_jwt_secret",
        "supabase_service_role_key",
        "ussd_webhook_secret",
        "sms_webhook_secret",
        "channel_hash_secret",
        "channel_election_id",
        "channel_simulator_enabled",
        "channel_callback_token",
        "africastalking_username",
        "africastalking_api_key",
        "africastalking_sender_id",
        mode="before",
    )
    @classmethod
    def blank_secret_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("supabase_jwt_secret", "auth_jwt_secret")
    @classmethod
    def jwt_secret_is_substantial(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("JWT secrets must be at least 32 characters")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        """Explicit origins. Outside production, `localhost` and `127.0.0.1` are the same
        development site to the browser, so each listed localhost origin also allows its
        127.0.0.1 twin. Production lists exactly what it is given."""
        if not self.cors_origins:
            return []
        origins = self.cors_origins.split(",")
        if not self.is_production:
            for origin in list(origins):
                if "//localhost:" in origin:
                    twin = origin.replace("//localhost:", "//127.0.0.1:", 1)
                    if twin not in origins:
                        origins.append(twin)
        return origins

    @field_validator(
        "ussd_webhook_secret", "sms_webhook_secret", "channel_hash_secret", "channel_callback_token"
    )
    @classmethod
    def channel_secret_is_substantial(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("Channel secrets must be at least 32 characters")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def simulator_enabled(self) -> bool:
        if self.channel_simulator_enabled is None:
            return not self.is_production
        return self.channel_simulator_enabled

    def assert_runtime_safe(self) -> None:
        """Production must not boot half-configured. Other environments may."""
        if not self.is_production:
            return
        missing = []
        if not self.database_url:
            missing.append("DATABASE_URL")
        if self.supabase_jwt_secret is None and self.auth_jwt_secret is None:
            missing.append("AUTH_JWT_SECRET (or SUPABASE_JWT_SECRET)")
        if not self.cors_origin_list:
            missing.append("CORS_ORIGINS")
        if self.evidence_storage != "supabase":
            missing.append("EVIDENCE_STORAGE=supabase")
        elif not (self.supabase_url and self.supabase_service_role_key):
            missing.append("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (evidence storage)")
        gateways = (
            self.ussd_webhook_secret or self.sms_webhook_secret or self.channel_callback_token
        )
        if gateways and not self.channel_hash_secret:
            missing.append("CHANNEL_HASH_SECRET (USSD and SMS gateways)")
        if self.channel_simulator_enabled:
            missing.append("CHANNEL_SIMULATOR_ENABLED must be false in production")
        if self.directory_source == "demo":
            missing.append("DIRECTORY_SOURCE=database (demo data is not allowed in production)")
        if missing:
            raise RuntimeError("Refusing to start in production. Missing: " + ", ".join(missing))


@lru_cache
def get_settings() -> Settings:
    return Settings()
