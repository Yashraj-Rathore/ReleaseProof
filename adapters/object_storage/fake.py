"""In-memory deterministic implementation of the bounded object-store port."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from packages.domain.object_storage import (
    ObjectChecksumMismatchError,
    ObjectConflictError,
    ObjectNotFoundError,
    ObjectStorageUnavailableError,
    StoredObjectMetadata,
    validate_object_input,
    validate_storage_key,
)


@dataclass(frozen=True, slots=True)
class _StoredObject:
    data: bytes
    metadata: StoredObjectMetadata


class FakeObjectStorage:
    def __init__(self, *, available: bool = True) -> None:
        self._available = available
        self._bucket_ready = False
        self._objects: dict[str, _StoredObject] = {}

    def set_available(self, available: bool) -> None:
        self._available = available

    def _require_available(self) -> None:
        if not self._available:
            raise ObjectStorageUnavailableError("fake object storage is unavailable")

    def _require_bucket(self) -> None:
        self._require_available()
        if not self._bucket_ready:
            raise ObjectStorageUnavailableError("object-storage bucket is not ready")

    def ensure_bucket(self) -> None:
        self._require_available()
        self._bucket_ready = True

    def put(self, key: str, data: bytes, *, content_type: str, sha256: str) -> StoredObjectMetadata:
        self._require_bucket()
        validate_storage_key(key)
        validate_object_input(data, content_type, sha256)
        actual_sha256 = hashlib.sha256(data).hexdigest()
        if actual_sha256 != sha256:
            raise ObjectChecksumMismatchError("supplied object checksum does not match bytes")
        metadata = StoredObjectMetadata(
            key=key,
            size=len(data),
            content_type=content_type,
            sha256=sha256,
        )
        existing = self._objects.get(key)
        if existing is not None:
            if existing.data == data and existing.metadata == metadata:
                return existing.metadata
            raise ObjectConflictError("immutable object key already contains different content")
        self._objects[key] = _StoredObject(data=bytes(data), metadata=metadata)
        return metadata

    def head(self, key: str) -> StoredObjectMetadata:
        self._require_bucket()
        validate_storage_key(key)
        try:
            return self._objects[key].metadata
        except KeyError as error:
            raise ObjectNotFoundError("object does not exist") from error

    def get(self, key: str) -> bytes:
        self._require_bucket()
        validate_storage_key(key)
        try:
            stored = self._objects[key]
        except KeyError as error:
            raise ObjectNotFoundError("object does not exist") from error
        if hashlib.sha256(stored.data).hexdigest() != stored.metadata.sha256:
            raise ObjectChecksumMismatchError("stored bytes do not match object metadata")
        return bytes(stored.data)

    def delete(self, key: str) -> None:
        self._require_bucket()
        validate_storage_key(key)
        self._objects.pop(key, None)
