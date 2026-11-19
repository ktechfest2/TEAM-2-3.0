"""Upload validation. The file's content decides its type, never its name or the
client-declared content type. Nothing here modifies the original bytes."""

import io
import re
import warnings
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from app.core.config import Settings
from app.core.errors import AppError

# Signature → (canonical MIME type, Pillow format name, allowed extensions)
_FORMATS: dict[str, tuple[str, str, frozenset[str]]] = {
    "jpeg": ("image/jpeg", "JPEG", frozenset({".jpg", ".jpeg"})),
    "png": ("image/png", "PNG", frozenset({".png"})),
    "webp": ("image/webp", "WEBP", frozenset({".webp"})),
}
ALLOWED_CONTENT_TYPES = frozenset(mime for mime, _, _ in _FORMATS.values())
# Hard ceiling on decoded pixels regardless of settings (decompression-bomb guard).
MAX_PIXELS = 80_000_000


@dataclass(frozen=True)
class ValidatedImage:
    content_type: str
    format: str
    width: int
    height: int
    byte_size: int
    original_filename: str | None


def _invalid(message: str, code: str = "invalid_image", status: int = 422) -> AppError:
    return AppError(code, message, status_code=status)


def sniff_format(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def safe_filename(name: str | None) -> str | None:
    if not name:
        return None
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:120]
    return cleaned or None


def validate_image(
    data: bytes,
    *,
    filename: str | None,
    declared_content_type: str | None,
    settings: Settings,
) -> ValidatedImage:
    if len(data) == 0:
        raise _invalid("The uploaded file is empty.")
    if len(data) > settings.evidence_max_bytes:
        raise _invalid(
            f"The image is larger than {settings.evidence_max_bytes // (1024 * 1024)} MB.",
            code="file_too_large",
            status=413,
        )

    kind = sniff_format(data)
    if kind is None:
        raise _invalid("Only JPEG, PNG and WebP photographs are accepted.", "unsupported_type", 415)
    mime, pil_format, extensions = _FORMATS[kind]

    clean_name = safe_filename(filename)
    if clean_name and "." in clean_name:
        extension = "." + clean_name.rsplit(".", 1)[-1].lower()
        if extension not in extensions:
            raise _invalid("The file extension does not match the image content.", "type_mismatch")
    if declared_content_type and declared_content_type.split(";")[0].strip().lower() not in {
        mime,
        "application/octet-stream",
        "",
    }:
        raise _invalid(
            "The declared content type does not match the image content.", "type_mismatch"
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                width, height = probe.size
                detected = probe.format
                if width * height > MAX_PIXELS:
                    raise _invalid("The image has too many pixels to process safely.")
                probe.verify()
            # verify() leaves the image unusable; a full decode catches truncated files.
            with Image.open(io.BytesIO(data)) as decoded:
                decoded.load()
    except AppError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        ValueError,
    ) as exc:
        raise _invalid("The image could not be read. It may be damaged or incomplete.") from exc

    if detected != pil_format:
        raise _invalid("The image content does not match its signature.", "type_mismatch")
    if min(width, height) < settings.evidence_min_dimension:
        raise _invalid(
            f"The photo is too small to read. The shorter side must be at least "
            f"{settings.evidence_min_dimension} pixels."
        )
    if max(width, height) > settings.evidence_max_dimension:
        raise _invalid(
            f"The photo is too large. The longer side must be at most "
            f"{settings.evidence_max_dimension} pixels."
        )

    return ValidatedImage(
        content_type=mime,
        format=kind,
        width=width,
        height=height,
        byte_size=len(data),
        original_filename=clean_name,
    )
