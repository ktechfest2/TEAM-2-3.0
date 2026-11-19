from fastapi import APIRouter

from app.core.config import get_settings
from app.db.session import check_database
from app.schemas.health import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    database = check_database()
    return HealthResponse(
        status="ok" if database != "unavailable" else "degraded",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        database=database,
    )
