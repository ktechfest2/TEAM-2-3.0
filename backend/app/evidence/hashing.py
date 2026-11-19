"""Fingerprints. Three hashes exist and must never be confused:

- original image hash: SHA-256 of the exact uploaded bytes (`sha256_bytes`);
- structured result hash: SHA-256 of the canonical result JSON (`result_fingerprint`);
- audit event hash: SHA-256 of a canonical audit event (see app/evidence/audit.py).
"""

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

RESULT_SCHEMA = "verivote.result.v1"
GENESIS_HASH = "0" * 64


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # Floats have no single canonical text form across databases and languages.
        raise TypeError("canonical JSON does not accept floats; use integers or strings")
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return canonical_timestamp(value)
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_canonical_value(item) for item in value]
    raise TypeError(f"unsupported type in canonical JSON: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    """Deterministic UTF-8 JSON: sorted keys, no whitespace, no floats."""
    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_timestamp(value: datetime) -> str:
    """UTC with microseconds. Naive values (SQLite round-trips) are treated as UTC."""
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical_result(
    *,
    election_id: uuid.UUID,
    polling_unit_id: uuid.UUID,
    template_id: str,
    values: Mapping[str, int | str | None],
) -> dict[str, Any]:
    """The structured result that is fingerprinted. Excludes transient metadata such as
    confidence scores, timestamps, reviewer identity and processing details."""
    return {
        "schema": RESULT_SCHEMA,
        "election_id": str(election_id),
        "polling_unit_id": str(polling_unit_id),
        "template_id": template_id,
        "fields": [[key, values[key]] for key in sorted(values)],
    }


def result_fingerprint(canonical: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(canonical))


def difference_hash(gray_pixels: Any) -> str:
    """64-bit dHash of a grayscale image (numpy array). Robust to re-encoding and mild
    resizing; used only to flag possible duplicate photos, never as proof."""
    import cv2
    import numpy as np

    small = cv2.resize(gray_pixels, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{int(np.uint64(value)):016x}"


def hamming_distance(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()
