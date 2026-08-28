"""Versioned, framework-light contracts for deterministic change intelligence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

DIFF_SCHEMA_VERSION = "change-diff-v1"
FEATURE_SCHEMA_VERSION = "change-features-v1"
GRAPH_SCHEMA_VERSION = "python-import-graph-v1"
HISTORY_SCHEMA_VERSION = "repository-history-v1"
EVIDENCE_SCHEMA_VERSION = "deterministic-risk-factor-v1"
EXTRACTOR_VERSION = "releaseproof-change-intel-v1"

type FeatureScalar = bool | int | float | str | None


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RawChangedFile:
    path: str
    additions: int
    deletions: int
    status: str = "modified"
    previous_path: str | None = None
    patch: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedFile:
    path: str
    previous_path: str | None
    additions: int
    deletions: int
    status: str
    language: str
    file_type: str
    patch: str | None
    patch_truncated: bool
    is_binary: bool
    is_generated: bool
    is_vendored: bool
    sensitive_tags: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "additions": self.additions,
            "deletions": self.deletions,
            "file_type": self.file_type,
            "is_binary": self.is_binary,
            "is_generated": self.is_generated,
            "is_vendored": self.is_vendored,
            "language": self.language,
            "patch": self.patch,
            "patch_truncated": self.patch_truncated,
            "path": self.path,
            "previous_path": self.previous_path,
            "sensitive_tags": list(self.sensitive_tags),
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class NormalizedDiff:
    schema_version: str
    files: tuple[NormalizedFile, ...]
    total_patch_bytes: int
    patch_set_truncated: bool
    diff_hash: str

    def as_dict(self) -> dict[str, object]:
        return {
            "diff_hash": self.diff_hash,
            "files": [item.as_dict() for item in self.files],
            "patch_set_truncated": self.patch_set_truncated,
            "schema_version": self.schema_version,
            "total_patch_bytes": self.total_patch_bytes,
        }


@dataclass(frozen=True, slots=True)
class SourceFile:
    path: str
    content: str


@dataclass(frozen=True, slots=True)
class SourceTree:
    repository_key: str
    revision: str
    files: tuple[SourceFile, ...]


class SourceTreeProviderError(RuntimeError):
    """A safe source-tree provider failure without raw source content."""


class SourceTreeProvider(Protocol):
    def get_tree(self, *, repository_key: str, revision: str) -> SourceTree: ...


@dataclass(frozen=True, slots=True)
class GraphFinding:
    code: str
    path: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail, "path": self.path}


@dataclass(frozen=True, slots=True)
class ImportGraph:
    schema_version: str
    available: bool
    modules: tuple[tuple[str, str], ...]
    edges: tuple[tuple[str, str], ...]
    findings: tuple[GraphFinding, ...]
    graph_hash: str

    def as_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "edges": [list(edge) for edge in self.edges],
            "findings": [finding.as_dict() for finding in self.findings],
            "graph_hash": self.graph_hash,
            "modules": [list(module) for module in self.modules],
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class BlastPath:
    changed_module: str
    affected_module: str
    distance: int
    modules: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "affected_module": self.affected_module,
            "changed_module": self.changed_module,
            "distance": self.distance,
            "modules": list(self.modules),
        }


@dataclass(frozen=True, slots=True)
class BlastRadius:
    graph_schema_version: str
    available: bool
    changed_modules: tuple[str, ...]
    direct_modules: tuple[str, ...]
    transitive_modules: tuple[str, ...]
    impacted_tests: tuple[str, ...]
    max_depth: int | None
    evidence_paths: tuple[BlastPath, ...]
    missing_changed_paths: tuple[str, ...]
    sensitive_tags: tuple[str, ...]
    truncated: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "changed_modules": list(self.changed_modules),
            "direct_modules": list(self.direct_modules),
            "evidence_paths": [path.as_dict() for path in self.evidence_paths],
            "graph_schema_version": self.graph_schema_version,
            "impacted_tests": list(self.impacted_tests),
            "max_depth": self.max_depth,
            "missing_changed_paths": list(self.missing_changed_paths),
            "sensitive_tags": list(self.sensitive_tags),
            "transitive_modules": list(self.transitive_modules),
            "truncated": self.truncated,
        }


@dataclass(frozen=True, slots=True)
class HistoricalFileChange:
    path: str
    additions: int
    deletions: int


@dataclass(frozen=True, slots=True)
class HistoricalChange:
    observed_at: datetime
    files: tuple[HistoricalFileChange, ...]
    author_key: str | None = None
    failed_check_proxy: bool | None = None


@dataclass(frozen=True, slots=True)
class HistoricalStatistics:
    schema_version: str
    prediction_time: datetime
    window_days: int
    included_changes: int
    excluded_future_changes: int
    target_file_touches: int
    target_module_touches: int
    line_churn: int
    prior_failure_proxy_count: int | None
    failure_proxy_observations: int
    ownership_familiarity: float | None
    missing: tuple[str, ...]
    truncated: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "excluded_future_changes": self.excluded_future_changes,
            "failure_proxy_observations": self.failure_proxy_observations,
            "included_changes": self.included_changes,
            "line_churn": self.line_churn,
            "missing": list(self.missing),
            "ownership_familiarity": self.ownership_familiarity,
            "prediction_time": self.prediction_time.isoformat(),
            "prior_failure_proxy_count": self.prior_failure_proxy_count,
            "schema_version": self.schema_version,
            "target_file_touches": self.target_file_touches,
            "target_module_touches": self.target_module_touches,
            "truncated": self.truncated,
            "window_days": self.window_days,
        }


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    name: str
    value_type: str
    default: FeatureScalar
    nullable: bool
    source: str

    def as_dict(self) -> dict[str, object]:
        return {
            "default": self.default,
            "name": self.name,
            "nullable": self.nullable,
            "source": self.source,
            "value_type": self.value_type,
        }


@dataclass(frozen=True, slots=True)
class FeatureSet:
    schema_version: str
    extractor_version: str
    values: dict[str, FeatureScalar]
    missing: dict[str, str]
    provenance: dict[str, str]
    feature_hash: str

    def as_dict(self) -> dict[str, object]:
        return {
            "extractor_version": self.extractor_version,
            "feature_hash": self.feature_hash,
            "missing": dict(sorted(self.missing.items())),
            "provenance": dict(sorted(self.provenance.items())),
            "schema_version": self.schema_version,
            "values": dict(sorted(self.values.items())),
        }


@dataclass(frozen=True, slots=True)
class RiskFactor:
    rule_id: str
    title: str
    value: FeatureScalar | dict[str, object]
    reason: str
    source_refs: tuple[str, ...]
    missing: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "missing": self.missing,
            "reason": self.reason,
            "rule_id": self.rule_id,
            "source_refs": list(self.source_refs),
            "title": self.title,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class ChangeIntelligenceResult:
    normalized_diff: NormalizedDiff
    graph: ImportGraph
    blast_radius: BlastRadius
    history: HistoricalStatistics
    features: FeatureSet
    risk_factors: tuple[RiskFactor, ...]
    result_hash: str

    def as_dict(self) -> dict[str, object]:
        return {
            "blast_radius": self.blast_radius.as_dict(),
            "features": self.features.as_dict(),
            "graph": self.graph.as_dict(),
            "history": self.history.as_dict(),
            "normalized_diff": self.normalized_diff.as_dict(),
            "result_hash": self.result_hash,
            "risk_factors": [factor.as_dict() for factor in self.risk_factors],
        }
