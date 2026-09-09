"""Framework-light immutable release and promotion contracts."""

from packages.release_core.contracts import (
    ARTIFACT_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    ArtifactIdentity,
    DatabaseRollbackStrategy,
    PromotionEvidence,
    PromotionStage,
    ReleaseManifest,
    RollbackEvidence,
    ServingDecision,
    ServingDecisionRecord,
    WorkloadBudget,
    canonical_json_bytes,
    validate_promotion,
    validate_rollback,
)

__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "ArtifactIdentity",
    "DatabaseRollbackStrategy",
    "PromotionEvidence",
    "PromotionStage",
    "ReleaseManifest",
    "RollbackEvidence",
    "ServingDecision",
    "ServingDecisionRecord",
    "WorkloadBudget",
    "canonical_json_bytes",
    "validate_promotion",
    "validate_rollback",
]
