"""Strict release, promotion, rollback and conditional-serving contracts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Final

MANIFEST_SCHEMA_VERSION: Final = "release-manifest-v1"
ARTIFACT_SCHEMA_VERSION: Final = "artifact-identity-v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_REVISION = re.compile(r"[0-9a-f]{40}")
_SAFE_VERSION = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._+@/-]{0,255}")


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def _validate_sha256(value: str, *, field: str) -> None:
    if _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256")


def _validate_image_digest(value: str) -> None:
    if not value.startswith("sha256:"):
        raise ValueError("application_image_digest must use sha256")
    _validate_sha256(value.removeprefix("sha256:"), field="application_image_digest")


class ServingDecision(StrEnum):
    KEEP_IN_WORKER = "KEEP_IN_WORKER"
    EXTRACT_FASTAPI = "EXTRACT_FASTAPI"
    KEEP_SIMPLE_SERVING = "KEEP_SIMPLE_SERVING"
    DEFER_INSUFFICIENT_EVIDENCE = "DEFER_INSUFFICIENT_EVIDENCE"


class PromotionStage(StrEnum):
    STAGING = "staging"
    PRODUCTION = "production"


class DatabaseRollbackStrategy(StrEnum):
    FORWARD_FIX_ONLY = "FORWARD_FIX_ONLY"


@dataclass(frozen=True)
class WorkloadBudget:
    worker_resident_memory_mib: int
    cold_start_ms: int
    steady_state_p95_ms: int
    minimum_throughput_per_second: float
    queue_delay_p95_ms: int
    maximum_incremental_monthly_cost_usd: float

    def __post_init__(self) -> None:
        values = asdict(self)
        if any(
            isinstance(value, bool) or not isinstance(value, int | float) or value <= 0
            for value in values.values()
        ):
            raise ValueError("all workload budgets must be positive numbers")


@dataclass(frozen=True)
class ServingDecisionRecord:
    component: str
    decision: ServingDecision
    workload: str
    budget: WorkloadBudget
    evidence_paths: tuple[str, ...]
    measured_dimensions: tuple[str, ...]
    missing_dimensions: tuple[str, ...]
    extraction_criteria_met: tuple[str, ...]
    operational_security_cost_accepted: bool
    rationale: tuple[str, ...]

    def __post_init__(self) -> None:
        if _SAFE_VERSION.fullmatch(self.component) is None:
            raise ValueError("component must be a bounded identifier")
        if not self.workload or len(self.workload) > 1_000:
            raise ValueError("workload must be present and bounded")
        if not self.evidence_paths or not self.rationale:
            raise ValueError("decision evidence and rationale are required")
        if self.decision is ServingDecision.EXTRACT_FASTAPI and (
            not self.extraction_criteria_met or not self.operational_security_cost_accepted
        ):
            raise ValueError("FastAPI extraction requires a measured criterion and accepted cost")
        if self.decision is ServingDecision.DEFER_INSUFFICIENT_EVIDENCE:
            if not self.missing_dimensions:
                raise ValueError("a deferral must name missing evidence")
            if self.operational_security_cost_accepted:
                raise ValueError("a deferred service cannot claim accepted operational cost")


@dataclass(frozen=True)
class ArtifactIdentity:
    name: str
    version: str
    sha256: str
    source_path: str
    schema_version: str = ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ARTIFACT_SCHEMA_VERSION:
            raise ValueError("unsupported artifact identity schema")
        if (
            _SAFE_VERSION.fullmatch(self.name) is None
            or _SAFE_VERSION.fullmatch(self.version) is None
        ):
            raise ValueError("artifact name and version must be bounded identifiers")
        _validate_sha256(self.sha256, field="artifact sha256")
        if (
            not self.source_path
            or self.source_path.startswith(("/", "\\"))
            or ".." in self.source_path.replace("\\", "/").split("/")
        ):
            raise ValueError("artifact source_path must be repository-relative")


@dataclass(frozen=True)
class ReleaseManifest:
    source_revision: str
    application_image_digest: str
    sbom: ArtifactIdentity
    active_model: ArtifactIdentity
    dataset: ArtifactIdentity
    model_registry_manifest_sha256: str
    dataset_manifest_sha256: str
    migration_tree_sha256: str
    evaluation_bundle_sha256: str
    build_provenance_sha256: str
    external_repository_execution_enabled: bool = False
    schema_version: str = MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported release manifest schema")
        if _REVISION.fullmatch(self.source_revision) is None:
            raise ValueError("source_revision must be a full lowercase Git commit SHA")
        _validate_image_digest(self.application_image_digest)
        for field, value in (
            ("model_registry_manifest_sha256", self.model_registry_manifest_sha256),
            ("dataset_manifest_sha256", self.dataset_manifest_sha256),
            ("migration_tree_sha256", self.migration_tree_sha256),
            ("evaluation_bundle_sha256", self.evaluation_bundle_sha256),
            ("build_provenance_sha256", self.build_provenance_sha256),
        ):
            _validate_sha256(value, field=field)
        if self.external_repository_execution_enabled:
            raise ValueError("M15 releases cannot enable external repository execution")

    def payload(self) -> dict[str, object]:
        return asdict(self)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True)
class PromotionEvidence:
    stage: PromotionStage
    release_manifest_sha256: str
    application_image_digest: str
    active_model_sha256: str
    migrations_passed: bool
    evaluations_passed: bool
    smoke_passed: bool
    compatibility_passed: bool
    protected_approval_reference: str

    def __post_init__(self) -> None:
        _validate_sha256(self.release_manifest_sha256, field="release_manifest_sha256")
        _validate_image_digest(self.application_image_digest)
        _validate_sha256(self.active_model_sha256, field="active_model_sha256")
        if not 1 <= len(self.protected_approval_reference) <= 256:
            raise ValueError("protected approval reference must be present and bounded")


@dataclass(frozen=True)
class RollbackEvidence:
    current_release_manifest_sha256: str
    target_release_manifest_sha256: str
    target_compatibility_passed: bool
    target_smoke_passed: bool
    database_strategy: DatabaseRollbackStrategy

    def __post_init__(self) -> None:
        _validate_sha256(
            self.current_release_manifest_sha256,
            field="current_release_manifest_sha256",
        )
        _validate_sha256(
            self.target_release_manifest_sha256,
            field="target_release_manifest_sha256",
        )


def validate_promotion(manifest: ReleaseManifest, evidence: PromotionEvidence) -> None:
    if evidence.release_manifest_sha256 != manifest.sha256:
        raise ValueError("promotion evidence targets a different release manifest")
    if evidence.application_image_digest != manifest.application_image_digest:
        raise ValueError("promotion evidence targets a different application image")
    if evidence.active_model_sha256 != manifest.active_model.sha256:
        raise ValueError("promotion evidence targets a different active model")
    if not all(
        (
            evidence.migrations_passed,
            evidence.evaluations_passed,
            evidence.smoke_passed,
            evidence.compatibility_passed,
        )
    ):
        raise ValueError("promotion requires migration, evaluation, smoke and compatibility gates")


def validate_rollback(evidence: RollbackEvidence) -> None:
    if evidence.current_release_manifest_sha256 == evidence.target_release_manifest_sha256:
        raise ValueError("rollback target must differ from the current release")
    if not evidence.target_compatibility_passed or not evidence.target_smoke_passed:
        raise ValueError("rollback requires compatibility and smoke evidence")
    if evidence.database_strategy is not DatabaseRollbackStrategy.FORWARD_FIX_ONLY:
        raise ValueError("database rollback must use forward-fix-only strategy")
