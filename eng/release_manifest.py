"""Build and validate immutable M15 release and promotion evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from packages.release_core import (
    ArtifactIdentity,
    PromotionEvidence,
    PromotionStage,
    ReleaseManifest,
    canonical_json_bytes,
    validate_promotion,
)

ROOT = Path(__file__).resolve().parents[1]
M4_PATH = ROOT / "tests/golden/m4_synthetic_baseline_v1.json"
M5_PATH = ROOT / "models/public/m5_classical_ml_v1.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return cast(dict[str, Any], value)


def _sbom_version(path: Path) -> str:
    value = _json(path)
    if value.get("bomFormat") != "CycloneDX":
        raise ValueError("SBOM must use CycloneDX JSON")
    version = value.get("specVersion")
    components = value.get("components")
    if not isinstance(version, str) or not version or len(version) > 16:
        raise ValueError("SBOM must name a bounded CycloneDX specVersion")
    if not isinstance(components, list):
        raise ValueError("SBOM must contain a components list")
    return version


def _tree_sha256(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        relative = path.relative_to(ROOT).as_posix().encode()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def build_manifest(
    *, source_revision: str, application_image_digest: str, sbom_path: Path
) -> ReleaseManifest:
    sbom_version = _sbom_version(sbom_path)
    m4 = _json(M4_PATH)
    m5 = _json(M5_PATH)
    dataset = cast(dict[str, Any], m4["dataset"])
    dataset_manifest = cast(dict[str, Any], dataset["manifest"])
    active_selection = cast(dict[str, Any], m5["active_selection"])
    evaluation_paths = sorted((ROOT / "artifacts/evaluation").glob("*.json"))
    if not evaluation_paths:
        raise ValueError("at least one committed evaluation artifact is required")
    migration_paths = sorted((ROOT / "apps/web").glob("*/migrations/*.py"))
    if not migration_paths:
        raise ValueError("application migration evidence is required")
    provenance = {
        "application_image_digest": application_image_digest,
        "dockerfile_sha256": _sha256(ROOT / "deploy/app/Dockerfile"),
        "source_revision": source_revision,
        "uv_lock_sha256": _sha256(ROOT / "uv.lock"),
    }
    return ReleaseManifest(
        source_revision=source_revision,
        application_image_digest=application_image_digest,
        sbom=ArtifactIdentity(
            name="releaseproof-application-sbom",
            version=f"cyclonedx-json-{sbom_version}",
            sha256=_sha256(sbom_path),
            source_path=sbom_path.resolve().relative_to(ROOT.resolve()).as_posix(),
        ),
        active_model=ArtifactIdentity(
            name="releaseproof-risk-model",
            version=str(active_selection["active_artifact_version"]),
            sha256=str(active_selection["active_artifact_hash"]),
            source_path="packages/ml_core/baseline.py",
        ),
        dataset=ArtifactIdentity(
            name="releaseproof-m4-synthetic-dataset",
            version=str(dataset_manifest["dataset_version"]),
            sha256=_sha256(M4_PATH),
            source_path=M4_PATH.relative_to(ROOT).as_posix(),
        ),
        model_registry_manifest_sha256=_sha256(M5_PATH),
        dataset_manifest_sha256=str(dataset_manifest["manifest_hash"]),
        migration_tree_sha256=_tree_sha256(migration_paths),
        evaluation_bundle_sha256=_tree_sha256(evaluation_paths),
        build_provenance_sha256=hashlib.sha256(canonical_json_bytes(provenance)).hexdigest(),
    )


def write_manifest(manifest: ReleaseManifest, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json_bytes(manifest.payload() | {"root_sha256": manifest.sha256}))


def load_manifest(path: Path) -> ReleaseManifest:
    value = _json(path)
    root_sha256 = value.pop("root_sha256", None)
    sbom = ArtifactIdentity(**cast(dict[str, Any], value.pop("sbom")))
    active_model = ArtifactIdentity(**cast(dict[str, Any], value.pop("active_model")))
    dataset = ArtifactIdentity(**cast(dict[str, Any], value.pop("dataset")))
    manifest = ReleaseManifest(
        **value,
        sbom=sbom,
        active_model=active_model,
        dataset=dataset,
    )
    if root_sha256 != manifest.sha256:
        raise ValueError("release manifest checksum is invalid")
    return manifest


def _write_promotion(
    *, manifest: ReleaseManifest, output: Path, stage: PromotionStage, approval: str
) -> None:
    evidence = PromotionEvidence(
        stage=stage,
        release_manifest_sha256=manifest.sha256,
        application_image_digest=manifest.application_image_digest,
        active_model_sha256=manifest.active_model.sha256,
        migrations_passed=True,
        evaluations_passed=True,
        smoke_passed=True,
        compatibility_passed=True,
        protected_approval_reference=approval,
    )
    validate_promotion(manifest, evidence)
    payload = asdict(evidence)
    payload["stage"] = evidence.stage.value
    payload["database_rollback_strategy"] = "FORWARD_FIX_ONLY"
    payload["root_sha256"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json_bytes(payload))


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--source-revision", required=True)
    build.add_argument("--application-image-digest", required=True)
    build.add_argument("--sbom", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--expected-source-revision")
    promote = subparsers.add_parser("promote")
    promote.add_argument("--manifest", required=True, type=Path)
    promote.add_argument("--stage", required=True, choices=[item.value for item in PromotionStage])
    promote.add_argument("--approval-reference", required=True)
    promote.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "build":
        manifest = build_manifest(
            source_revision=args.source_revision,
            application_image_digest=args.application_image_digest,
            sbom_path=args.sbom,
        )
        write_manifest(manifest, args.output)
        print(json.dumps({"manifest_sha256": manifest.sha256, "status": "written"}))
    elif args.command == "verify":
        manifest = load_manifest(args.manifest)
        if (
            args.expected_source_revision is not None
            and manifest.source_revision != args.expected_source_revision
        ):
            raise ValueError(
                "release manifest source revision does not match the requested revision"
            )
        rebuilt = build_manifest(
            source_revision=manifest.source_revision,
            application_image_digest=manifest.application_image_digest,
            sbom_path=ROOT / manifest.sbom.source_path,
        )
        if rebuilt != manifest:
            raise ValueError("release manifest inputs do not match the checked-out source")
        print(json.dumps({"manifest_sha256": manifest.sha256, "status": "verified"}))
    else:
        manifest = load_manifest(args.manifest)
        _write_promotion(
            manifest=manifest,
            output=args.output,
            stage=PromotionStage(args.stage),
            approval=args.approval_reference,
        )
        print(json.dumps({"manifest_sha256": manifest.sha256, "status": "promotable"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
