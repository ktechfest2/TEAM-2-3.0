import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.errors import error_response, register_exception_handlers
from app.core.logging import request_id_ctx, setup_logging
from app.core.rate_limit import SlidingWindowLimiter, client_key
from app.db.session import dispose_engine

_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_access_logger = logging.getLogger("verivote.access")

def create_app() -> FastAPI:
    settings = get_settings()
    settings.assert_runtime_safe()
    setup_logging(settings)

    app = FastAPI(
        title="VoteTrace API",
        version=settings.app_version,
        summary="Electoral evidence and result verification.",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
        lifespan=_lifespan,
    )

    limiter = SlidingWindowLimiter(settings.rate_limit_per_minute)

    # Registered first so it runs inside CORS: a 429 still carries CORS headers.
    @app.middleware("http")
    async def rate_limit(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path.startswith("/api/v1/") and request.method != "OPTIONS":
            allowed, retry_after = limiter.check(client_key(request, settings.trust_proxy_headers))
            if not allowed:
                response = error_response(
                    status_code=429,
                    code="rate_limited",
                    message="Too many requests. Please wait and try again.",
                    request_id=request_id_ctx.get(),
                )
                response.headers["Retry-After"] = str(retry_after)
                return response
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-Request-ID",
            "Idempotency-Key",
            "X-Content-SHA256",
            "Last-Event-ID",
        ],
        expose_headers=["X-Request-ID", "X-Content-SHA256"],
        max_age=600,
    )

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Cache-Control"] = "no-store"
            if settings.is_production:
                response.headers["Strict-Transport-Security"] = (
                    "max-age=63072000; includeSubDomains"
                )
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            _access_logger.info(
                "request method=%s path=%s status=%s duration_ms=%s request_id=%s",
                request.method,
                request.url.path[:200],
                response.status_code,
                elapsed_ms,
                request_id,
            )
            return response
        finally:
            request_id_ctx.reset(token)

    register_exception_handlers(app)
    app.include_router(v1_router, prefix="/api/v1")
    return app

async def _lifespan(_app: FastAPI):
    yield
    dispose_engine()

app = create_app()
