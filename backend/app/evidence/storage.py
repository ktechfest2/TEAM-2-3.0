"""Private evidence storage. Objects are addressed by opaque keys; nothing here
produces a public URL. Reads verify the stored SHA-256 before returning bytes."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.evidence.hashing import sha256_bytes


class IntegrityError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "evidence_integrity_failure",
            "The stored evidence no longer matches its recorded fingerprint.",
            status_code=409,
        )


class StorageUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "storage_unavailable", "Evidence storage is temporarily unavailable.", status_code=503
        )


class EvidenceStorage(Protocol):
    bucket: str

    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def signed_url(self, key: str, expires_in: int) -> str | None: ...


def read_verified(storage: EvidenceStorage, key: str, expected_sha256: str) -> bytes:
    data = storage.get(key)
    if sha256_bytes(data) != expected_sha256:
        raise IntegrityError()
    return data


class LocalStorage:
    """Development and test storage in a private directory outside any web root."""

    def __init__(self, root: str, bucket: str) -> None:
        self.bucket = bucket
        self.root = Path(root).resolve() / bucket

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("invalid storage key")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Exclusive create: evidence objects are write-once.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise AppError("evidence_missing", "The evidence file is missing.", 410) from exc

    def signed_url(self, key: str, expires_in: int) -> str | None:
        return None


class SupabaseStorage:
    """Private Supabase Storage bucket, accessed only from the API with the service-role
    key. The key never leaves the server."""

    def __init__(
        self,
        base_url: str,
        service_key: str,
        bucket: str,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.bucket = bucket
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/storage/v1",
            headers={"Authorization": f"Bearer {service_key}", "apikey": service_key},
            timeout=timeout,
            transport=transport,
        )

    def _object(self, key: str) -> str:
        return f"/object/{quote(self.bucket)}/{quote(key)}"

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            response = self._client.post(
                self._object(key),
                content=data,
                headers={"Content-Type": content_type, "x-upsert": "false"},
            )
        except httpx.HTTPError as exc:
            raise StorageUnavailableError() from exc
        if response.status_code >= 400:
            raise StorageUnavailableError()

    def get(self, key: str) -> bytes:
        try:
            response = self._client.get(self._object(key))
        except httpx.HTTPError as exc:
            raise StorageUnavailableError() from exc
        if response.status_code == 404:
            raise AppError("evidence_missing", "The evidence file is missing.", 410)
        if response.status_code >= 400:
            raise StorageUnavailableError()
        return response.content

    def signed_url(self, key: str, expires_in: int) -> str | None:
        try:
            response = self._client.post(
                f"/object/sign/{quote(self.bucket)}/{quote(key)}", json={"expiresIn": expires_in}
            )
        except httpx.HTTPError as exc:
            raise StorageUnavailableError() from exc
        if response.status_code >= 400:
            raise StorageUnavailableError()
        signed = response.json().get("signedURL")
        return f"{self._client.base_url}{signed}" if isinstance(signed, str) else None


def build_storage(settings: Settings) -> EvidenceStorage:
    if settings.evidence_storage == "supabase":
        if not (settings.supabase_url and settings.supabase_service_role_key):
            raise StorageUnavailableError()
        return SupabaseStorage(
            settings.supabase_url,
            settings.supabase_service_role_key.get_secret_value(),
            settings.evidence_bucket,
        )
    return LocalStorage(settings.evidence_local_dir, settings.evidence_bucket)


@lru_cache
def _cached_storage(storage: str, local_dir: str, bucket: str) -> EvidenceStorage:
    return build_storage(get_settings())


def get_storage() -> EvidenceStorage:
    settings = get_settings()
    return _cached_storage(
        settings.evidence_storage, settings.evidence_local_dir, settings.evidence_bucket
    )
