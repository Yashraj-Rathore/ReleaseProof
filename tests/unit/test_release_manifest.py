from __future__ import annotations

from pathlib import Path

import pytest

from eng.release_manifest import build_manifest, load_manifest, write_manifest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SBOM = ROOT / "tests/fixtures/release/m15_cyclonedx_sbom.json"


def test_release_manifest_build_and_load_recomputes_immutable_inputs(tmp_path: Path) -> None:
    manifest = build_manifest(
        source_revision="c" * 40,
        application_image_digest=f"sha256:{'d' * 64}",
        sbom_path=FIXTURE_SBOM,
    )
    output = tmp_path / "release-manifest.json"

    write_manifest(manifest, output)

    assert load_manifest(output) == manifest
    assert manifest.sbom.version == "cyclonedx-json-1.6"
    assert manifest.external_repository_execution_enabled is False


def test_release_manifest_rejects_non_cyclonedx_sbom(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"components": []}', encoding="utf-8")

    with pytest.raises(ValueError, match="CycloneDX"):
        build_manifest(
            source_revision="c" * 40,
            application_image_digest=f"sha256:{'d' * 64}",
            sbom_path=invalid,
        )
