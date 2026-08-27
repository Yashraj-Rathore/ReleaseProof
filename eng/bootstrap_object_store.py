#!/usr/bin/env python3
"""Idempotently create and verify the configured bounded S3 bucket."""

from __future__ import annotations

import json
import sys

from adapters.object_storage import S3ObjectStorage, S3Settings
from packages.domain import ObjectStorageError


def main() -> int:
    try:
        storage = S3ObjectStorage(S3Settings.from_environment())
        storage.ensure_bucket()
    except (ObjectStorageError, ValueError):
        print("object-store bootstrap failed", file=sys.stderr)
        return 1
    print(json.dumps({"object_store": "ready"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
