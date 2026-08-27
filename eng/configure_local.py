#!/usr/bin/env python3
"""Generate ignored local service configuration from explicit environment values."""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEAWEEDFS_CONFIG = ROOT / "deploy" / "seaweedfs" / "s3.local.json"


def _credential(name: str) -> str:
    value = os.getenv(name, "")
    if not value or len(value) > 128 or any(ord(character) < 33 for character in value):
        raise ValueError(f"{name} must contain 1..128 non-whitespace printable characters")
    return value


def render_seaweedfs_config(access_key: str, secret_key: str) -> str:
    if not access_key or not secret_key:
        raise ValueError("SeaweedFS local credentials cannot be empty")
    config = {
        "identities": [
            {
                "name": "releaseproof-local",
                "credentials": [{"accessKey": access_key, "secretKey": secret_key}],
                "actions": ["Admin", "Read", "Write", "List", "Tagging"],
            }
        ]
    }
    return json.dumps(config, indent=2) + "\n"


def main() -> int:
    access_key = _credential("S3_ACCESS_KEY_ID")
    secret_key = _credential("S3_SECRET_ACCESS_KEY")
    SEAWEEDFS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    SEAWEEDFS_CONFIG.write_text(
        render_seaweedfs_config(access_key, secret_key), encoding="utf-8", newline="\n"
    )
    SEAWEEDFS_CONFIG.chmod(0o600)
    print("wrote ignored SeaweedFS local configuration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
