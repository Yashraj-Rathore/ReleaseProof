from __future__ import annotations

import hashlib
import os

import pytest

from adapters.object_storage import S3ObjectStorage, S3Settings
from packages.domain import ObjectChecksumMismatchError, ObjectConflictError, ObjectNotFoundError

pytestmark = pytest.mark.integration


def test_seaweedfs_satisfies_bounded_object_storage_contract() -> None:
    if os.getenv("RUN_S3_INTEGRATION") != "1":
        pytest.skip("set RUN_S3_INTEGRATION=1 with the Compose stack running")

    storage = S3ObjectStorage(S3Settings.from_environment())
    key = "contract-tests/immutable-object.txt"
    data = b"releaseproof seaweedfs contract fixture"
    checksum = hashlib.sha256(data).hexdigest()

    storage.ensure_bucket()
    storage.ensure_bucket()
    storage.delete(key)
    metadata = storage.put(key, data, content_type="text/plain", sha256=checksum)
    try:
        assert storage.head(key) == metadata
        assert storage.get(key) == data
        assert storage.put(key, data, content_type="text/plain", sha256=checksum) == metadata
        with pytest.raises(ObjectConflictError):
            storage.put(
                key,
                b"different",
                content_type="text/plain",
                sha256=hashlib.sha256(b"different").hexdigest(),
            )
        with pytest.raises(ObjectChecksumMismatchError):
            storage.put(
                "contract-tests/bad-checksum.txt",
                data,
                content_type="text/plain",
                sha256="0" * 64,
            )
    finally:
        storage.delete(key)

    with pytest.raises(ObjectNotFoundError):
        storage.get(key)
