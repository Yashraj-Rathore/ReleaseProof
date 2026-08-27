from __future__ import annotations

import hashlib

import pytest

from adapters.object_storage import FakeObjectStorage
from packages.domain import (
    ObjectChecksumMismatchError,
    ObjectConflictError,
    ObjectNotFoundError,
    ObjectStorageUnavailableError,
)


def test_fake_object_storage_bounded_contract() -> None:
    storage = FakeObjectStorage()
    data = b"immutable fixture bytes"
    checksum = hashlib.sha256(data).hexdigest()

    with pytest.raises(ObjectStorageUnavailableError):
        storage.head("fixture/object.txt")

    storage.ensure_bucket()
    storage.ensure_bucket()
    created = storage.put("fixture/object.txt", data, content_type="text/plain", sha256=checksum)

    assert (
        storage.put("fixture/object.txt", data, content_type="text/plain", sha256=checksum)
        == created
    )
    assert storage.head("fixture/object.txt") == created
    assert storage.get("fixture/object.txt") == data

    with pytest.raises(ObjectConflictError):
        storage.put(
            "fixture/object.txt",
            b"different",
            content_type="text/plain",
            sha256=hashlib.sha256(b"different").hexdigest(),
        )

    storage.delete("fixture/object.txt")
    storage.delete("fixture/object.txt")
    with pytest.raises(ObjectNotFoundError):
        storage.get("fixture/object.txt")


def test_fake_object_storage_rejects_checksum_mismatch_and_traversal() -> None:
    storage = FakeObjectStorage()
    storage.ensure_bucket()

    with pytest.raises(ObjectChecksumMismatchError):
        storage.put("fixture/object.txt", b"bytes", content_type="text/plain", sha256="0" * 64)
    with pytest.raises(ValueError, match="normalized relative path"):
        storage.head("../secret")


def test_fake_object_storage_has_explicit_unavailable_error() -> None:
    storage = FakeObjectStorage(available=False)

    with pytest.raises(ObjectStorageUnavailableError):
        storage.ensure_bucket()
