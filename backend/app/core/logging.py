import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime

from app.core.config import Settings

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

_SENSITIVE_KEY = re.compile(
    r"password|passwd|secret|token|authorization|cookie|api[_-]?key|credential|service[_-]?role|jwt",
    re.IGNORECASE,
)
_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
_URL_USERINFO = re.compile(r"://[^/\s:]+:[^@\s]+@")
_QUERY_SECRET = re.compile(r"(?i)(password|token|secret|api_key|access_token)=([^&\s]+)")


def redact_text(value: str) -> str:
    value = _BEARER.sub("Bearer [redacted]", value)
    value = _URL_USERINFO.sub("://[redacted]@", value)
    return _QUERY_SECRET.sub(r"\1=[redacted]", value)


def redact(value: object) -> object:
    """Drop secret-bearing mapping keys before anything is logged or returned."""
    if isinstance(value, dict):
        cleaned: dict[object, object] = {}
        for key, item in value.items():
            if isinstance(key, str) and _SENSITIVE_KEY.search(key):
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = redact(item)
        return cleaned
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
            "request_id": getattr(record, "request_id", None),
        }
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def setup_logging(settings: Settings) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    logging.captureWarnings(True)
