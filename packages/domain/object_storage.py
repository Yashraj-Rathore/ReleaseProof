"""Bounded, provider-neutral immutable object-storage contract from ADR-016."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

MAX_OBJECT_SIZE_BYTES = 25 * 1024 * 1024
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ObjectStorageError(RuntimeError):
    """Base object-storage boundary error."""


class ObjectNotFoundError(ObjectStorageError):
    """The requested object does not exist."""


class ObjectConflictError(ObjectStorageError):
    """An immutable key already contains different bytes or metadata."""


class ObjectChecksumMismatchError(ObjectStorageError):
    """Stored or supplied bytes do not match their declared SHA-256."""


class ObjectStorageUnavailableError(ObjectStorageError):
    """The provider is unavailable or returned an unsupported response."""


def validate_storage_key(key: str) -> None:
    segments = key.replace("\\", "/").split("/")
    if (
        not key
        or len(key) > 1_024
        or key.startswith(("/", "\\"))
        or any(segment in {"", ".", ".."} for segment in segments)
        or any(ord(character) < 32 for character in key)
    ):
        raise ValueError("object key must be a bounded normalized relative path")


def validate_object_input(data: bytes, content_type: str, sha256: str) -> None:
    if len(data) > MAX_OBJECT_SIZE_BYTES:
        raise ValueError("object exceeds the 25 MiB M1 limit")
    if not content_type or len(content_type) > 255 or any(ord(c) < 32 for c in content_type):
        raise ValueError("content_type must contain 1..255 printable characters")
    if not _SHA256_PATTERN.fullmatch(sha256):
        raise ValueError("sha256 must be 64 lowercase hexadecimal characters")


@dataclass(frozen=True, slots=True)
class StoredObjectMetadata:
    key: str
    size: int
    content_type: str
    sha256: str

    def __post_init__(self) -> None:
        validate_storage_key(self.key)
        if self.size < 0 or self.size > MAX_OBJECT_SIZE_BYTES:
            raise ValueError("stored object size is outside the M1 limit")
        validate_object_input(b"", self.content_type, self.sha256)


class ObjectStorage(Protocol):
    def ensure_bucket(self) -> None: ...

    def put(
        self, key: str, data: bytes, *, content_type: str, sha256: str
    ) -> StoredObjectMetadata: ...

    def head(self, key: str) -> StoredObjectMetadata: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...
