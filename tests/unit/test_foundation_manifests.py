from __future__ import annotations

import json
import re
from pathlib import Path

from eng.configure_local import render_seaweedfs_config
from eng.update_file_inventory import _canonical_bytes

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_IMAGES = {
    "pgvector/pgvector:0.8.6-pg18-trixie@sha256:"
    "78bf48b801e792f99e3ac62b5036fd3876e9be48afda16c1e331af1c75ceb2ff",
    "redis:8.10.1-alpine@sha256:becdda6c7f4b3fb42e42fd7f120bbf5c54c4caaaf16f26da24e4563d2c1f0576",
    "chrislusf/seaweedfs:4.44@sha256:"
    "e67e8c385484120b78bff47ba5f4debbca47fbd27ed1a39f016f47e8baea615b",
}


def _example_environment() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, value = line.split("=", maxsplit=1)
            values[name] = value
    return values


def test_compose_images_are_exact_and_ports_are_loopback_only() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert {
        line.strip().removeprefix("image: ") for line in compose.splitlines() if "image:" in line
    } == EXPECTED_IMAGES
    assert compose.count('"127.0.0.1:${') == 3
    assert "postgres_data:/var/lib/postgresql\n" in compose
    assert "postgres_data:/var/lib/postgresql/data" not in compose
    assert "dir/status?pretty=y" in compose
    assert '"Url": "seaweedfs:8080"' in compose


def test_local_seaweedfs_config_is_rendered_from_environment_template() -> None:
    environment = _example_environment()
    config = json.loads(
        render_seaweedfs_config(
            environment["S3_ACCESS_KEY_ID"], environment["S3_SECRET_ACCESS_KEY"]
        )
    )
    credential = config["identities"][0]["credentials"][0]

    assert credential["accessKey"] == environment["S3_ACCESS_KEY_ID"]
    assert credential["secretKey"] == environment["S3_SECRET_ACCESS_KEY"]
    assert environment["S3_ENDPOINT_URL"] == "http://localhost:8333"
    assert "deploy/seaweedfs/s3.local.json" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "deploy/seaweedfs/s3.local.json" in (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "SEAWEEDFS_CONFIG.chmod(0o600)" in (ROOT / "eng" / "configure_local.py").read_text(
        encoding="utf-8"
    )


def test_ci_external_actions_are_pinned_to_full_commit_shas() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    action_references = re.findall(r"uses:\s+([^\s#]+)", workflow)

    assert action_references
    assert all(re.search(r"@[0-9a-f]{40}$", reference) for reference in action_references)
    configure = "uv run --env-file .env.example python -m eng.configure_local"
    public_ci_mode = "chmod 0644 deploy/seaweedfs/s3.local.json"
    assert (
        workflow.index(configure)
        < workflow.index(public_ci_mode)
        < workflow.index("docker compose config --quiet")
    )
    postgres_suite = 'uv run --env-file .env.example pytest -m "not integration"'
    postgres_settings = "--ds=apps.web.releaseproof.settings.base"
    postgres_test_secret = "GITHUB_WEBHOOK_SECRET: releaseproof-ci-test-webhook-secret"  # noqa: S105
    assert (
        workflow.index("docker compose up -d --wait")
        < workflow.index(postgres_test_secret)
        < workflow.index(postgres_suite)
        < workflow.index(postgres_settings)
    )
    assert workflow.index(postgres_settings) < workflow.index(
        "uv run --env-file .env.example python -m eng.bootstrap_object_store"
    )


def test_file_inventory_normalizes_text_line_endings() -> None:
    assert _canonical_bytes(b"first\nsecond\n") == b"first\nsecond\n"
    assert _canonical_bytes(b"first\r\nsecond\r\n") == b"first\nsecond\n"
    assert _canonical_bytes(b"\xff\r\n\x00") == b"\xff\r\n\x00"


def test_fixture_repository_records_synthetic_provenance_and_license() -> None:
    fixture = ROOT / "tests" / "fixtures" / "repositories" / "releaseproof_fixture"
    manifest = json.loads((fixture / "fixture-manifest.json").read_text(encoding="utf-8"))

    assert manifest["synthetic"] is True
    assert manifest["license_spdx"] == "MIT"
    assert (fixture / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")
