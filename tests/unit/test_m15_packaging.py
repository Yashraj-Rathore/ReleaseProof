from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_application_image_is_multi_stage_non_root_and_does_not_embed_runner() -> None:
    dockerfile = (ROOT / "deploy/app/Dockerfile").read_text(encoding="utf-8")

    assert dockerfile.count("python:3.13.15-slim-bookworm@sha256:") == 2
    assert " AS builder" in dockerfile
    assert " AS runtime" in dockerfile
    assert "USER 65532:65532" in dockerfile
    assert '"gunicorn==26.2.0"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "COPY runner" not in dockerfile
    assert "COPY tests" not in dockerfile
    assert "COPY models/private" not in dockerfile
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "!artifacts/evaluation/m13_governance_eval_v1.json" in dockerignore


def test_compose_has_migration_first_health_gated_application_services() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    for service in ("migration:", "web:", "worker:"):
        assert f"  {service}" in compose
    assert "condition: service_completed_successfully" in compose
    assert "releaseproof-app:m15" in compose
    assert '"127.0.0.1:${WEB_PORT:-8000}:8000"' in compose
    assert compose.count("no-new-privileges:true") >= 7
    assert compose.count("cap_drop:") >= 7
    assert 'SANDBOX_ENABLED: "false"' in compose
    assert "docker.sock" not in compose


def test_ci_scans_exact_image_emits_sbom_and_validates_release_manifest() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "aquasecurity/trivy-action@a9c7b0f06e461e9d4b4d1711f154ee024b8d7ab8" in workflow
    assert "version: v0.74.0" in workflow
    assert "scanners: vuln" in workflow
    assert "scanners: secret" in workflow
    assert "image-ref: releaseproof-app:m15" in workflow
    assert "format: cyclonedx" in workflow
    assert "eng.release_manifest build" in workflow
    assert "eng.release_manifest verify" in workflow


def test_release_workflow_requires_protected_staging_then_production() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "environment: staging" in workflow
    assert "environment: production" in workflow
    assert "needs: staging" in workflow
    assert "FORWARD_FIX_ONLY" in workflow
    assert "kubectl" not in workflow
    assert "docker push" not in workflow
