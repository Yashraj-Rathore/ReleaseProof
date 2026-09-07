"""Framework-light M13 experiment, registry, feedback, and drift governance."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlparse

from packages.change_intel import canonical_hash

FORMAL_EXPERIMENT_SCHEMA_VERSION = "formal-experiment-v1"
EVALUATION_REGISTRY_SCHEMA_VERSION = "evaluation-registry-entry-v1"
MODEL_ARTIFACT_SCHEMA_VERSION = "governed-model-artifact-v1"
MODEL_LIFECYCLE_POLICY_VERSION = "model-lifecycle-v1"
DEPLOYMENT_OUTCOME_SCHEMA_VERSION = "deployment-outcome-v1"
DRIFT_POLICY_VERSION = "data-quality-drift-policy-v1"
DRIFT_ASSESSMENT_SCHEMA_VERSION = "data-quality-drift-assessment-v1"

_SHA256_LENGTH = 64
_REQUIRED_COMPATIBILITY_CHECKS = frozenset(
    {
        "artifact_checksum",
        "evaluation_gate",
        "feature_schema",
        "input_schema",
        "privacy_license",
        "runtime",
    }
)

type SafeScalar = str | int | float | bool


class GovernanceError(ValueError):
    """Raised when governance evidence is incomplete, unsafe, or contradictory."""


class ExperimentKind(StrEnum):
    HEURISTIC = "heuristic"
    CLASSICAL = "classical"
    SEMANTIC = "semantic"
    RETRIEVAL = "retrieval"
    LLM = "llm"
    AGENT = "agent"


class DataScope(StrEnum):
    PUBLIC_SYNTHETIC = "public_synthetic"
    PUBLIC_APPROVED = "public_approved"
    ORGANIZATION_LOCAL = "organization_local"


class EvaluationComponent(StrEnum):
    RETRIEVAL = "retrieval"
    LLM = "llm"
    AGENT = "agent"


class ModelLifecycle(StrEnum):
    CANDIDATE = "candidate"
    STAGING = "staging"
    ACTIVE = "active"
    RETIRED = "retired"


class LifecycleAction(StrEnum):
    REGISTER = "register"
    PROMOTE_TO_STAGING = "promote_to_staging"
    ACTIVATE = "activate"
    RETIRE = "retire"
    ROLLBACK = "rollback"


class OutcomeKind(StrEnum):
    NO_ISSUE = "no_issue"
    REVERT = "revert"
    HOTFIX = "hotfix"
    INCIDENT = "incident"
    MANUAL_LABEL = "manual_label"
    UNKNOWN = "unknown"


class DriftDecision(StrEnum):
    PASS = "pass"  # noqa: S105 - a policy decision, not a credential
    REVIEW = "review"
    INSUFFICIENT_DATA = "insufficient_data"
    INCOMPATIBLE_SCHEMA = "incompatible_schema"


def _is_sha256(value: str) -> bool:
    return len(value) == _SHA256_LENGTH and all(
        character in "0123456789abcdef" for character in value
    )


def _bounded_text(value: str, *, field: str, maximum: int = 256) -> None:
    if (
        not 1 <= len(value) <= maximum
        or not value.isascii()
        or any(ord(char) < 32 for char in value)
    ):
        raise GovernanceError(f"{field} must be bounded printable ASCII")


def _checksum(value: str, *, field: str) -> None:
    if not _is_sha256(value):
        raise GovernanceError(f"{field} must be a lowercase SHA-256")


def _code_sha(value: str) -> None:
    if len(value) not in {40, 64} or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise GovernanceError("code_sha must be a lowercase immutable Git SHA")


def _safe_mapping(
    values: Mapping[str, SafeScalar], *, field: str, maximum_items: int
) -> dict[str, SafeScalar]:
    if not 1 <= len(values) <= maximum_items:
        raise GovernanceError(f"{field} must contain 1..{maximum_items} values")
    normalized: dict[str, SafeScalar] = {}
    for key, value in values.items():
        _bounded_text(key, field=f"{field} key", maximum=128)
        if isinstance(value, float) and not math.isfinite(value):
            raise GovernanceError(f"{field} values must be finite")
        if isinstance(value, str):
            _bounded_text(value, field=f"{field} value", maximum=512)
        normalized[key] = value
    return dict(sorted(normalized.items()))


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    role: str
    uri: str
    sha256: str

    def __post_init__(self) -> None:
        _bounded_text(self.role, field="artifact role", maximum=64)
        _bounded_text(self.uri, field="artifact URI", maximum=1_024)
        parsed = urlparse(self.uri)
        if parsed.scheme not in {"artifact", "s3", "mlflow-artifacts"}:
            raise GovernanceError("artifact URI scheme is not allowlisted")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise GovernanceError("artifact URI cannot contain credentials, query, or fragment")
        _checksum(self.sha256, field="artifact checksum")

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "sha256": self.sha256, "uri": self.uri}


@dataclass(frozen=True, slots=True)
class FormalExperimentRecord:
    experiment_name: str
    run_name: str
    kind: ExperimentKind
    dataset_version: str
    dataset_manifest_sha256: str
    feature_schema_version: str
    code_sha: str
    parameters: Mapping[str, SafeScalar]
    metrics: Mapping[str, float]
    environment: Mapping[str, SafeScalar]
    artifacts: tuple[ArtifactReference, ...]
    data_scope: DataScope
    synthetic: bool
    contains_customer_code: bool = False
    schema_version: str = FORMAL_EXPERIMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != FORMAL_EXPERIMENT_SCHEMA_VERSION:
            raise GovernanceError("formal experiment schema is unsupported")
        _bounded_text(self.experiment_name, field="experiment name", maximum=128)
        _bounded_text(self.run_name, field="run name", maximum=128)
        _bounded_text(self.dataset_version, field="dataset version", maximum=128)
        _checksum(self.dataset_manifest_sha256, field="dataset manifest checksum")
        _bounded_text(self.feature_schema_version, field="feature schema version", maximum=128)
        _code_sha(self.code_sha)
        _safe_mapping(self.parameters, field="experiment parameters", maximum_items=64)
        _safe_mapping(self.metrics, field="experiment metrics", maximum_items=64)
        _safe_mapping(self.environment, field="experiment environment", maximum_items=64)
        if not 1 <= len(self.artifacts) <= 32:
            raise GovernanceError("formal experiment must name 1..32 immutable artifacts")
        if len({item.role for item in self.artifacts}) != len(self.artifacts):
            raise GovernanceError("formal experiment artifact roles must be unique")
        if self.contains_customer_code and self.data_scope is not DataScope.ORGANIZATION_LOCAL:
            raise GovernanceError("customer code cannot be recorded in a shared/public experiment")
        if self.synthetic != (self.data_scope is DataScope.PUBLIC_SYNTHETIC):
            raise GovernanceError("synthetic flag and data scope disagree")

    def as_dict(self) -> dict[str, object]:
        return {
            "artifacts": [item.as_dict() for item in self.artifacts],
            "code_sha": self.code_sha,
            "contains_customer_code": self.contains_customer_code,
            "data_scope": self.data_scope.value,
            "dataset_manifest_sha256": self.dataset_manifest_sha256,
            "dataset_version": self.dataset_version,
            "environment": _safe_mapping(
                self.environment, field="experiment environment", maximum_items=64
            ),
            "experiment_name": self.experiment_name,
            "feature_schema_version": self.feature_schema_version,
            "kind": self.kind.value,
            "metrics": _safe_mapping(self.metrics, field="experiment metrics", maximum_items=64),
            "parameters": _safe_mapping(
                self.parameters, field="experiment parameters", maximum_items=64
            ),
            "run_name": self.run_name,
            "schema_version": self.schema_version,
            "synthetic": self.synthetic,
        }

    @property
    def record_sha256(self) -> str:
        return canonical_hash(self.as_dict())


@dataclass(frozen=True, slots=True)
class EvaluationRegistryEntry:
    component: EvaluationComponent
    evaluation_dataset_version: str
    evaluation_dataset_sha256: str
    configuration_versions: Mapping[str, SafeScalar]
    aggregate_metrics: Mapping[str, float]
    result_artifact: ArtifactReference
    license_spdx: str
    synthetic: bool
    contains_customer_code: bool = False
    schema_version: str = EVALUATION_REGISTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EVALUATION_REGISTRY_SCHEMA_VERSION:
            raise GovernanceError("evaluation registry schema is unsupported")
        _bounded_text(
            self.evaluation_dataset_version, field="evaluation dataset version", maximum=128
        )
        _checksum(self.evaluation_dataset_sha256, field="evaluation dataset checksum")
        _safe_mapping(
            self.configuration_versions,
            field="evaluation configuration",
            maximum_items=32,
        )
        _safe_mapping(self.aggregate_metrics, field="aggregate metrics", maximum_items=64)
        _bounded_text(self.license_spdx, field="evaluation license", maximum=64)
        if self.contains_customer_code:
            raise GovernanceError("shared evaluation registry cannot contain customer code")

    def as_dict(self) -> dict[str, object]:
        return {
            "aggregate_metrics": _safe_mapping(
                self.aggregate_metrics, field="aggregate metrics", maximum_items=64
            ),
            "component": self.component.value,
            "configuration_versions": _safe_mapping(
                self.configuration_versions,
                field="evaluation configuration",
                maximum_items=32,
            ),
            "contains_customer_code": self.contains_customer_code,
            "evaluation_dataset_sha256": self.evaluation_dataset_sha256,
            "evaluation_dataset_version": self.evaluation_dataset_version,
            "license_spdx": self.license_spdx,
            "result_artifact": self.result_artifact.as_dict(),
            "schema_version": self.schema_version,
            "synthetic": self.synthetic,
        }

    @property
    def record_sha256(self) -> str:
        return canonical_hash(self.as_dict())


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    checks: Mapping[str, bool]
    report_sha256: str

    def __post_init__(self) -> None:
        if set(self.checks) != _REQUIRED_COMPATIBILITY_CHECKS:
            raise GovernanceError("compatibility report must contain the exact required checks")
        if not all(isinstance(value, bool) for value in self.checks.values()):
            raise GovernanceError("compatibility checks must be booleans")
        expected = canonical_hash(dict(sorted(self.checks.items())))
        if self.report_sha256 != expected:
            raise GovernanceError("compatibility report checksum is invalid")

    @property
    def passed(self) -> bool:
        return all(self.checks.values())

    def as_dict(self) -> dict[str, object]:
        return {
            "checks": dict(sorted(self.checks.items())),
            "passed": self.passed,
            "report_sha256": self.report_sha256,
        }


@dataclass(frozen=True, slots=True)
class PromotionApproval:
    artifact_sha256: str
    approved_action: LifecycleAction
    reviewer_id: str
    reviewer_role: str
    reason: str
    evaluation_sha256: str
    compatibility: CompatibilityReport

    def __post_init__(self) -> None:
        _checksum(self.artifact_sha256, field="approved artifact checksum")
        if not isinstance(self.approved_action, LifecycleAction):
            raise GovernanceError("approved action is invalid")
        _bounded_text(self.reviewer_id, field="reviewer ID", maximum=128)
        if self.reviewer_role not in {"owner", "admin"}:
            raise GovernanceError("model transitions require Owner/Admin approval")
        _bounded_text(self.reason, field="approval reason", maximum=1_000)
        _checksum(self.evaluation_sha256, field="evaluation checksum")

    def as_dict(self) -> dict[str, object]:
        return {
            "approved_action": self.approved_action.value,
            "artifact_sha256": self.artifact_sha256,
            "compatibility": self.compatibility.as_dict(),
            "evaluation_sha256": self.evaluation_sha256,
            "reason": self.reason,
            "reviewer_id": self.reviewer_id,
            "reviewer_role": self.reviewer_role,
        }

    @property
    def approval_sha256(self) -> str:
        return canonical_hash(self.as_dict())


def validate_model_transition(
    *,
    current: ModelLifecycle | None,
    target: ModelLifecycle,
    action: LifecycleAction,
    approval: PromotionApproval | None,
) -> None:
    expected = {
        (None, ModelLifecycle.CANDIDATE): LifecycleAction.REGISTER,
        (ModelLifecycle.CANDIDATE, ModelLifecycle.STAGING): LifecycleAction.PROMOTE_TO_STAGING,
        (ModelLifecycle.STAGING, ModelLifecycle.ACTIVE): LifecycleAction.ACTIVATE,
        (ModelLifecycle.ACTIVE, ModelLifecycle.RETIRED): LifecycleAction.RETIRE,
        (ModelLifecycle.RETIRED, ModelLifecycle.ACTIVE): LifecycleAction.ROLLBACK,
    }.get((current, target))
    if expected is None or action is not expected:
        raise GovernanceError("model lifecycle transition is not allowed")
    if action is LifecycleAction.REGISTER:
        if approval is not None:
            raise GovernanceError("candidate registration does not accept promotion approval")
        return
    if approval is None or not approval.compatibility.passed:
        raise GovernanceError("model transition requires approved passing compatibility evidence")
    if approval.approved_action is not action:
        raise GovernanceError("model approval does not authorize this lifecycle action")


@dataclass(frozen=True, slots=True)
class FeedbackEligibility:
    organization_training_eligible: bool
    shared_training_eligible: bool
    reason: str


def evaluate_feedback_eligibility(
    *,
    snapshot_created_at: datetime,
    observation_window_started_at: datetime,
    observation_window_ended_at: datetime,
    signal_observed_at: datetime,
    ingested_at: datetime,
    outcome: OutcomeKind,
    provenance_known: bool,
    organization_learning_enabled: bool,
    explicit_learning_opt_in: bool,
) -> FeedbackEligibility:
    timestamps = (
        snapshot_created_at,
        observation_window_started_at,
        observation_window_ended_at,
        signal_observed_at,
        ingested_at,
    )
    if any(value.tzinfo is None or value.utcoffset() is None for value in timestamps):
        raise GovernanceError("feedback timestamps must be timezone aware")
    if observation_window_started_at < snapshot_created_at:
        raise GovernanceError("outcome window cannot start before the prediction snapshot")
    if observation_window_ended_at <= observation_window_started_at:
        raise GovernanceError("outcome window must have positive duration")
    if not observation_window_started_at <= signal_observed_at <= observation_window_ended_at:
        raise GovernanceError("outcome signal must fall inside its declared observation window")
    if ingested_at < observation_window_ended_at:
        raise GovernanceError("deployment outcome cannot be ingested before its window completes")
    if outcome is OutcomeKind.UNKNOWN or not provenance_known:
        reason = "outcome_or_provenance_unknown"
        eligible = False
    elif not organization_learning_enabled:
        reason = "organization_learning_disabled"
        eligible = False
    elif not explicit_learning_opt_in:
        reason = "outcome_not_explicitly_opted_in"
        eligible = False
    else:
        reason = "eligible_for_organization_local_learning"
        eligible = True
    return FeedbackEligibility(
        organization_training_eligible=eligible,
        shared_training_eligible=False,
        reason=reason,
    )


@dataclass(frozen=True, slots=True)
class FeatureProfile:
    name: str
    row_count: int
    missing_count: int
    histogram: tuple[int, ...]

    def __post_init__(self) -> None:
        _bounded_text(self.name, field="feature name", maximum=128)
        if self.row_count < 1 or not 0 <= self.missing_count <= self.row_count:
            raise GovernanceError("feature profile counts are invalid")
        if not 2 <= len(self.histogram) <= 50 or any(value < 0 for value in self.histogram):
            raise GovernanceError("feature histogram must contain 2..50 non-negative bins")
        if sum(self.histogram) != self.row_count - self.missing_count:
            raise GovernanceError("feature histogram count does not match non-missing rows")

    @property
    def missing_rate(self) -> float:
        return self.missing_count / self.row_count

    def as_dict(self) -> dict[str, object]:
        return {
            "histogram": list(self.histogram),
            "missing_count": self.missing_count,
            "missing_rate": round(self.missing_rate, 12),
            "name": self.name,
            "row_count": self.row_count,
        }


@dataclass(frozen=True, slots=True)
class PerformanceProfile:
    metric_name: str
    value: float
    labeled_row_count: int

    def __post_init__(self) -> None:
        _bounded_text(self.metric_name, field="performance metric", maximum=128)
        if not math.isfinite(self.value):
            raise GovernanceError("performance metric must be finite")
        if self.labeled_row_count < 0:
            raise GovernanceError("labeled row count cannot be negative")


@dataclass(frozen=True, slots=True)
class MonitoringProfile:
    feature_schema_version: str
    features: tuple[FeatureProfile, ...]
    performance: PerformanceProfile | None = None

    def __post_init__(self) -> None:
        _bounded_text(self.feature_schema_version, field="feature schema version", maximum=128)
        if not self.features or len(self.features) > 256:
            raise GovernanceError("monitoring profile must contain 1..256 features")
        if len({feature.name for feature in self.features}) != len(self.features):
            raise GovernanceError("monitoring feature names must be unique")
        if len({feature.row_count for feature in self.features}) != 1:
            raise GovernanceError("monitoring features must describe one shared row set")

    @property
    def row_count(self) -> int:
        return self.features[0].row_count

    def as_dict(self) -> dict[str, object]:
        return {
            "feature_schema_version": self.feature_schema_version,
            "features": [feature.as_dict() for feature in self.features],
            "performance": None
            if self.performance is None
            else {
                "labeled_row_count": self.performance.labeled_row_count,
                "metric_name": self.performance.metric_name,
                "value": self.performance.value,
            },
            "row_count": self.row_count,
        }

    @property
    def profile_sha256(self) -> str:
        return canonical_hash(self.as_dict())


@dataclass(frozen=True, slots=True)
class DriftPolicy:
    minimum_rows: int = 100
    minimum_labeled_rows: int = 100
    maximum_missingness_delta: float = 0.10
    maximum_population_stability_index: float = 0.20
    maximum_performance_drop: float = 0.05
    version: str = DRIFT_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.version != DRIFT_POLICY_VERSION:
            raise GovernanceError("drift policy version is unsupported")
        if self.minimum_rows < 2 or self.minimum_labeled_rows < 2:
            raise GovernanceError("drift minimum sample sizes are invalid")
        for value in (
            self.maximum_missingness_delta,
            self.maximum_population_stability_index,
            self.maximum_performance_drop,
        ):
            if not math.isfinite(value) or value < 0:
                raise GovernanceError("drift thresholds must be finite and non-negative")

    def as_dict(self) -> dict[str, object]:
        return {
            "maximum_missingness_delta": self.maximum_missingness_delta,
            "maximum_performance_drop": self.maximum_performance_drop,
            "maximum_population_stability_index": self.maximum_population_stability_index,
            "minimum_labeled_rows": self.minimum_labeled_rows,
            "minimum_rows": self.minimum_rows,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class DriftAssessment:
    decision: DriftDecision
    reason_codes: tuple[str, ...]
    schema_match: bool
    row_count: int
    missingness_delta: Mapping[str, float]
    population_stability_index: Mapping[str, float]
    performance_drop: float | None
    reference_profile_sha256: str
    current_profile_sha256: str
    policy: DriftPolicy
    human_review_required: bool
    automatic_retraining_allowed: bool = False
    automatic_promotion_allowed: bool = False
    schema_version: str = DRIFT_ASSESSMENT_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "automatic_promotion_allowed": self.automatic_promotion_allowed,
            "automatic_retraining_allowed": self.automatic_retraining_allowed,
            "current_profile_sha256": self.current_profile_sha256,
            "decision": self.decision.value,
            "human_review_required": self.human_review_required,
            "missingness_delta": dict(sorted(self.missingness_delta.items())),
            "policy": self.policy.as_dict(),
            "population_stability_index": dict(sorted(self.population_stability_index.items())),
            "performance_drop": self.performance_drop,
            "reason_codes": list(self.reason_codes),
            "reference_profile_sha256": self.reference_profile_sha256,
            "row_count": self.row_count,
            "schema_match": self.schema_match,
            "schema_version": self.schema_version,
        }

    @property
    def assessment_sha256(self) -> str:
        return canonical_hash(self.as_dict())


def _population_stability_index(reference: tuple[int, ...], current: tuple[int, ...]) -> float:
    if len(reference) != len(current):
        raise GovernanceError("drift histograms must use identical versioned bins")
    reference_total = sum(reference)
    current_total = sum(current)
    if reference_total == 0 or current_total == 0:
        raise GovernanceError("drift histograms require observed non-missing values")
    epsilon = 1e-6
    score = 0.0
    for reference_count, current_count in zip(reference, current, strict=True):
        reference_fraction = max(reference_count / reference_total, epsilon)
        current_fraction = max(current_count / current_total, epsilon)
        score += (current_fraction - reference_fraction) * math.log(
            current_fraction / reference_fraction
        )
    return score


def assess_drift(
    *, reference: MonitoringProfile, current: MonitoringProfile, policy: DriftPolicy
) -> DriftAssessment:
    reference_by_name = {feature.name: feature for feature in reference.features}
    current_by_name = {feature.name: feature for feature in current.features}
    schema_match = (
        reference.feature_schema_version == current.feature_schema_version
        and reference_by_name.keys() == current_by_name.keys()
    )
    if not schema_match:
        return DriftAssessment(
            decision=DriftDecision.INCOMPATIBLE_SCHEMA,
            reason_codes=("feature_schema_mismatch",),
            schema_match=False,
            row_count=current.row_count,
            missingness_delta={},
            population_stability_index={},
            performance_drop=None,
            reference_profile_sha256=reference.profile_sha256,
            current_profile_sha256=current.profile_sha256,
            policy=policy,
            human_review_required=True,
        )
    missingness = {
        name: round(current_by_name[name].missing_rate - reference_by_name[name].missing_rate, 12)
        for name in sorted(reference_by_name)
    }
    psi = {
        name: round(
            _population_stability_index(
                reference_by_name[name].histogram,
                current_by_name[name].histogram,
            ),
            12,
        )
        for name in sorted(reference_by_name)
    }
    performance_drop: float | None = None
    performance_sufficient = False
    if reference.performance is not None and current.performance is not None:
        if reference.performance.metric_name != current.performance.metric_name:
            raise GovernanceError("performance metric identities must match")
        performance_drop = round(reference.performance.value - current.performance.value, 12)
        performance_sufficient = (
            reference.performance.labeled_row_count >= policy.minimum_labeled_rows
            and current.performance.labeled_row_count >= policy.minimum_labeled_rows
        )
    reason_codes: list[str] = []
    if any(abs(value) > policy.maximum_missingness_delta for value in missingness.values()):
        reason_codes.append("missingness_shift")
    if any(value > policy.maximum_population_stability_index for value in psi.values()):
        reason_codes.append("distribution_shift")
    if (
        performance_sufficient
        and performance_drop is not None
        and performance_drop > policy.maximum_performance_drop
    ):
        reason_codes.append("performance_shift")
    data_sufficient = (
        reference.row_count >= policy.minimum_rows and current.row_count >= policy.minimum_rows
    )
    if not data_sufficient:
        reason_codes.append("insufficient_feature_rows")
    if (reference.performance is None) != (current.performance is None) or (
        reference.performance is not None and not performance_sufficient
    ):
        reason_codes.append("insufficient_labeled_outcomes")
    if not data_sufficient or "insufficient_labeled_outcomes" in reason_codes:
        decision = DriftDecision.INSUFFICIENT_DATA
    elif (
        "missingness_shift" in reason_codes
        or "distribution_shift" in reason_codes
        or "performance_shift" in reason_codes
    ):
        decision = DriftDecision.REVIEW
    else:
        decision = DriftDecision.PASS
    return DriftAssessment(
        decision=decision,
        reason_codes=tuple(reason_codes),
        schema_match=True,
        row_count=current.row_count,
        missingness_delta=missingness,
        population_stability_index=psi,
        performance_drop=performance_drop,
        reference_profile_sha256=reference.profile_sha256,
        current_profile_sha256=current.profile_sha256,
        policy=policy,
        human_review_required=decision is not DriftDecision.PASS,
    )
