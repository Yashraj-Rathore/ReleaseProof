"""Bounded smoke for the production-shaped Compose web and migration paths."""

from __future__ import annotations

import json
import os
from urllib.parse import urlparse
from urllib.request import urlopen

import django
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


def _base_url() -> str:
    value = os.getenv("RELEASEPROOF_WEB_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("RELEASEPROOF_WEB_BASE_URL must be a loopback HTTP URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("RELEASEPROOF_WEB_BASE_URL must not contain credentials/query/fragment")
    return value


def _probe(url: str, *, expected_status: str) -> None:
    with urlopen(url, timeout=5) as response:  # noqa: S310 - loopback URL is validated above.
        if response.status != 200:
            raise RuntimeError(f"deployment probe returned HTTP {response.status}")
        payload = json.loads(response.read(1_024))
    if payload != {"status": expected_status}:
        raise RuntimeError("deployment probe returned an unexpected bounded payload")


def main() -> int:
    base_url = _base_url()
    _probe(f"{base_url}/health/live", expected_status="ok")
    _probe(f"{base_url}/health/ready", expected_status="ready")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apps.web.releaseproof.settings.base")
    django.setup()
    executor = MigrationExecutor(connection)
    if executor.migration_plan(executor.loader.graph.leaf_nodes()):
        raise RuntimeError("deployment has unapplied migrations")
    print(json.dumps({"migrations": "current", "status": "ready"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
