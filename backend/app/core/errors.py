import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import redact, request_id_ctx

logger = logging.getLogger("verivote.errors")

# Validation payloads include the submitted value. These keys can carry secrets.
_DROPPED_ERROR_KEYS = {"input", "ctx", "url"}


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None) or request_id_ctx.get()


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str | None,
    details: Any = None,
) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if request_id:
        body["request_id"] = request_id
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content={"error": body})


def _safe_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for issue in exc.errors():
        safe.append(
            {key: redact(value) for key, value in issue.items() if key not in _DROPPED_ERROR_KEYS}
        )
    return safe


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            request_id=_request_id(request),
            details=redact(exc.details) if exc.details is not None else None,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
        }.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return error_response(
            status_code=exc.status_code,
            code=code,
            message=message,
            request_id=_request_id(request),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            status_code=422,
            code="validation_error",
            message="The request is invalid.",
            request_id=_request_id(request),
            details=_safe_validation_errors(exc),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # The exception object can embed a database URL. Log only the type.
        logger.error("unhandled error type=%s", type(exc).__name__)
        return error_response(
            status_code=500,
            code="internal_error",
            message="Something went wrong.",
            request_id=_request_id(request),
        )
