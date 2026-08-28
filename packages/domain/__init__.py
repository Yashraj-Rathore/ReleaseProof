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
from packages.domain.tasks import TaskMessage, TaskPublisher, TaskPublisherError

__all__ = (
    "MAX_OBJECT_SIZE_BYTES",
    "ObjectChecksumMismatchError",
    "ObjectConflictError",
    "ObjectNotFoundError",
    "ObjectStorage",
    "ObjectStorageError",
    "ObjectStorageUnavailableError",
    "StoredObjectMetadata",
    "TaskMessage",
    "TaskPublisher",
    "TaskPublisherError",
)
