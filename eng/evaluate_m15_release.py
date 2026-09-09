"""Reproduce the deterministic M15 packaging and conditional-serving evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from packages.release_core import (
    ServingDecision,
    ServingDecisionRecord,
    WorkloadBudget,
    canonical_json_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "artifacts/evaluation/m15_release_eval_v1.json"
M14_PATH = ROOT / "artifacts/evaluation/m14_operations_eval_v1.json"
TRIVY_ACTION_SHA = "a9c7b0f06e461e9d4b4d1711f154ee024b8d7ab8"
TRIVY_VERSION = "0.74.0"
GUNICORN_VERSION = "26.2.0"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return cast(dict[str, Any], value)


def _decision_records() -> list[dict[str, object]]:
    common_budget = WorkloadBudget(
        worker_resident_memory_mib=768,
        cold_start_ms=10_000,
        steady_state_p95_ms=250,
        minimum_throughput_per_second=4.0,
        queue_delay_p95_ms=2_000,
        maximum_incremental_monthly_cost_usd=75.0,
    )
    records = (
        ServingDecisionRecord(
            component="fastapi-model-service",
            decision=ServingDecision.DEFER_INSUFFICIENT_EVIDENCE,
            workload=(
                "Active deterministic heuristic scoring for a bounded PR feature record; planned "
                "comparison assumes two worker replicas and no GPU."
            ),
            budget=common_budget,
            evidence_paths=(
                "docs/20_PERFORMANCE_CAPACITY_COST.md",
                "artifacts/evaluation/m14_operations_eval_v1.json",
            ),
            measured_dimensions=("synthetic_control_plane_p95_ms",),
            missing_dimensions=(
                "worker_resident_model_memory_mib",
                "worker_cold_start_ms",
                "broker_queue_delay_p95_ms",
                "independent_inference_scaling_cost",
            ),
            extraction_criteria_met=(),
            operational_security_cost_accepted=False,
            rationale=(
                "No learned model is active or resident in each worker.",
                "M14 explicitly excludes worker RSS, broker scheduling and saturation evidence.",
                "A new authenticated service would add a trust boundary without measured benefit.",
            ),
        ),
        ServingDecisionRecord(
            component="ollama-local-provider",
            decision=ServingDecision.DEFER_INSUFFICIENT_EVIDENCE,
            workload=(
                "Organization-approved local advisory generation under the existing strict schema."
            ),
            budget=common_budget,
            evidence_paths=(
                "docs/11_LLM_PROVIDER_ABSTRACTION.md",
                "docs/20_PERFORMANCE_CAPACITY_COST.md",
            ),
            measured_dimensions=(),
            missing_dimensions=(
                "approved_local_privacy_demand",
                "compatible_hardware",
                "model_license_review",
                "schema_and_grounding_evaluation",
            ),
            extraction_criteria_met=(),
            operational_security_cost_accepted=False,
            rationale=(
                "The deterministic fake remains the default and hosted transmission is "
                "policy-gated.",
                "No approved local model, hardware profile or representative privacy workload "
                "exists.",
            ),
        ),
        ServingDecisionRecord(
            component="vllm-gpu-serving",
            decision=ServingDecision.DEFER_INSUFFICIENT_EVIDENCE,
            workload="Batched local advisory inference using an approved immutable model revision.",
            budget=common_budget,
            evidence_paths=(
                "docs/20_PERFORMANCE_CAPACITY_COST.md",
                "docs/26_TECHNOLOGY_BASELINE.md",
            ),
            measured_dimensions=(),
            missing_dimensions=(
                "failing_simple_serving_baseline",
                "approved_gpu_hardware",
                "model_license_review",
                "privacy_review",
                "throughput_and_cost_comparison",
            ),
            extraction_criteria_met=(),
            operational_security_cost_accepted=False,
            rationale=(
                "No local serving baseline fails a predeclared budget.",
                "No GPU runtime, approved model or measured batching benefit exists.",
            ),
        ),
    )
    result: list[dict[str, object]] = []
    for record in records:
        value = asdict(record)
        value["decision"] = record.decision.value
        normalized: Any = json.loads(json.dumps(value))
        if not isinstance(normalized, dict):
            raise ValueError("serving decision did not serialize to an object")
        result.append(cast(dict[str, object], normalized))
    return result


def build_artifact() -> dict[str, object]:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "deploy/app/Dockerfile").read_text(encoding="utf-8")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release_workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    m14 = _json(M14_PATH)
    m14_root = m14.get("root_sha256")
    if not isinstance(m14_root, str):
        raise ValueError("M14 evidence is missing its root checksum")
    return {
        "schema_version": "m15-release-evaluation-v1",
        "synthetic": True,
        "production_packaging": {
            "application_image": "releaseproof-app:m15",
            "base_image_digest_pinned": "python:3.13.15-slim-bookworm@sha256:" in dockerfile,
            "multi_stage": " AS builder" in dockerfile and " AS runtime" in dockerfile,
            "non_root_uid": "USER 65532:65532" in dockerfile,
            "gunicorn_version": GUNICORN_VERSION,
            "compose_services": ["migration", "web", "worker"],
            "migration_dependency_gate": "condition: service_completed_successfully" in compose,
            "health_checks": compose.count("healthcheck:") >= 6,
            "external_repository_execution_enabled": False,
        },
        "conditional_serving_decisions": _decision_records(),
        "supply_chain": {
            "trivy_action_commit": TRIVY_ACTION_SHA,
            "trivy_version": TRIVY_VERSION,
            "dependency_scan": "scanners: vuln" in ci,
            "secret_scan": "scanners: secret" in ci,
            "image_scan": "image-ref: releaseproof-app:m15" in ci,
            "cyclonedx_sbom": "format: cyclonedx" in ci,
            "release_manifest_check": "eng.release_manifest build" in ci,
            "protected_environments": all(
                f"environment: {name}" in release_workflow for name in ("staging", "production")
            ),
        },
        "promotion_and_rollback": {
            "same_image_and_model_digests_required": True,
            "ordered_gates": ["migrations", "evaluations", "smoke", "compatibility", "approval"],
            "database_rollback_strategy": "FORWARD_FIX_ONLY",
            "automatic_database_reverse_allowed": False,
            "cloud_deployment_adapter_present": False,
        },
        "manifest_inputs": {
            "dataset": {
                "path": "tests/golden/m4_synthetic_baseline_v1.json",
                "sha256": _sha256(ROOT / "tests/golden/m4_synthetic_baseline_v1.json"),
            },
            "model_registry": {
                "path": "models/public/m5_classical_ml_v1.json",
                "sha256": _sha256(ROOT / "models/public/m5_classical_ml_v1.json"),
            },
            "m14_operations": {
                "path": "artifacts/evaluation/m14_operations_eval_v1.json",
                "root_sha256": m14_root,
            },
        },
        "claims": {
            "production_capacity_validated": False,
            "cloud_deployment_validated": False,
            "fastapi_required": False,
            "ollama_validated": False,
            "vllm_validated": False,
            "kubernetes_approved": False,
        },
        "limitations": [
            "Compose is a production-shaped loopback demo, not a highly available deployment.",
            "Trivy results depend on the vulnerability database available during each CI run.",
            "The repository emits unsigned local provenance; registry-backed OIDC attestation is "
            "deferred until a registry and deployment target are selected.",
            "GitHub environment reviewers and branch rules are repository settings and must be "
            "configured by an Owner before a real promotion.",
            "No external repository code, paid provider, model download, GPU or Kubernetes "
            "was used.",
        ],
    }


def _with_hash(value: dict[str, object]) -> dict[str, object]:
    return value | {"root_sha256": hashlib.sha256(canonical_json_bytes(value)).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("choose exactly one of --write or --check")
    artifact = _with_hash(build_artifact())
    if args.write:
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_bytes(canonical_json_bytes(artifact))
        print(f"wrote {ARTIFACT_PATH.relative_to(ROOT)}")
    else:
        committed = _json(ARTIFACT_PATH)
        if committed != artifact:
            raise ValueError("committed M15 release evidence does not reproduce")
        print(json.dumps({"root_sha256": artifact["root_sha256"], "status": "verified"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
