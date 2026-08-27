#!/usr/bin/env python3
"""Exercise the bounded S3 put/head/get/delete path without logging credentials."""

from __future__ import annotations

import hashlib
import json
import sys

from adapters.object_storage import S3ObjectStorage, S3Settings
from packages.domain import ObjectStorageError


def main() -> int:
    key = "m1-smoke/object-store.txt"
    data = b"releaseproof-object-store-contract"
    checksum = hashlib.sha256(data).hexdigest()
    try:
        storage = S3ObjectStorage(S3Settings.from_environment())
        storage.ensure_bucket()
        metadata = storage.put(key, data, content_type="text/plain", sha256=checksum)
        downloaded = storage.get(key)
        storage.delete(key)
    except (ObjectStorageError, ValueError):
        print("object-store smoke failed", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "bytes": len(downloaded),
                "object_store": "contract-ok",
                "sha256": metadata.sha256,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
