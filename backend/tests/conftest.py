import os

# Set before the application is imported so boot-time settings are test values.
os.environ["APP_ENV"] = "test"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
os.environ["SUPABASE_JWT_SECRET"] = "test-secret-test-secret-test-secret"
os.environ["AUTH_JWT_SECRET"] = "local-test-secret-local-test-secret-local"
os.environ["DATABASE_URL"] = ""
os.environ["DIRECTORY_SOURCE"] = "demo"
os.environ["OCR_PROVIDER"] = "none"
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

get_settings.cache_clear()

@pytest.fixture()
def client() -> Iterator[TestClient]:
    get_settings.cache_clear()
    application = create_app()
    with TestClient(application, raise_server_exceptions=False) as test_client:
        yield test_client
