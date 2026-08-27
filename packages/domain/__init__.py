"""Shared framework-light domain contracts."""

from packages.domain.object_storage import (
    MAX_OBJECT_SIZE_BYTES,
    ObjectChecksumMismatchError,
    ObjectConflictError,
    ObjectNotFoundError,
    ObjectStorage,
    ObjectStorageError,
    ObjectStorageUnavailableError,
    StoredObjectMetadata,
)

__all__ = (
    "MAX_OBJECT_SIZE_BYTES",
    "ObjectChecksumMismatchError",
    "ObjectConflictError",
    "ObjectNotFoundError",
    "ObjectStorage",
    "ObjectStorageError",
    "ObjectStorageUnavailableError",
    "StoredObjectMetadata",
)
