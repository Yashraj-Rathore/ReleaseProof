"""Prediction-time feature schema v1 and deterministic evidence rendering."""

from __future__ import annotations

import math
from collections import Counter

from packages.change_intel.contracts import (
    EVIDENCE_SCHEMA_VERSION,
    EXTRACTOR_VERSION,
    FEATURE_SCHEMA_VERSION,
    BlastRadius,
    FeatureDefinition,
    FeatureScalar,
    FeatureSet,
    HistoricalStatistics,
    NormalizedDiff,
    RiskFactor,
    canonical_hash,
)

FEATURE_DEFINITIONS = (
    FeatureDefinition("files_changed", "integer", 0, False, "snapshot.changed_files"),
    FeatureDefinition("lines_added", "integer", 0, False, "snapshot.changed_files"),
    FeatureDefinition("lines_deleted", "integer", 0, False, "snapshot.changed_files"),
    FeatureDefinition("python_files_changed", "integer", 0, False, "normalized_diff"),
    FeatureDefinition("test_files_changed", "integer", 0, False, "normalized_diff"),
    FeatureDefinition("migration_files_changed", "integer", 0, False, "normalized_diff"),
    FeatureDefinition("dependency_files_changed", "integer", 0, False, "normalized_diff"),
    FeatureDefinition("sensitive_files_changed", "integer", 0, False, "normalized_diff"),
    FeatureDefinition("renamed_files", "integer", 0, False, "normalized_diff"),
    FeatureDefinition("deleted_files", "integer", 0, False, "normalized_diff"),
    FeatureDefinition("binary_files", "integer", 0, False, "normalized_diff"),
    FeatureDefinition("generated_files", "integer", 0, False, "normalized_diff"),
    FeatureDefinition("vendored_files", "integer", 0, False, "normalized_diff"),
    FeatureDefinition("change_concentration", "float", 0.0, False, "normalized_diff"),
    FeatureDefinition("change_entropy", "float", 0.0, False, "normalized_diff"),
    FeatureDefinition("commit_count", "integer", None, True, "snapshot.commit_count"),
    FeatureDefinition("blast_direct_modules", "integer", None, True, "python_graph"),
    FeatureDefinition("blast_transitive_modules", "integer", None, True, "python_graph"),
    FeatureDefinition("blast_impacted_tests", "integer", None, True, "python_graph"),
    FeatureDefinition("blast_max_depth", "integer", None, True, "python_graph"),
    FeatureDefinition("historical_file_touches_90d", "integer", None, True, "pre_change_history"),
    FeatureDefinition("historical_module_touches_90d", "integer", None, True, "pre_change_history"),
    FeatureDefinition("historical_line_churn_90d", "integer", None, True, "pre_change_history"),
    FeatureDefinition("prior_failure_proxy_count_90d", "integer", None, True, "pre_change_history"),
    FeatureDefinition("ownership_familiarity_90d", "float", None, True, "pre_change_history"),
)


def _distribution(normalized_diff: NormalizedDiff) -> tuple[float, float]:
    changes = [file.additions + file.deletions for file in normalized_diff.files]
    total = sum(changes)
    if not changes or total == 0:
        return 0.0, 0.0
    proportions = [change / total for change in changes if change]
    concentration = max(proportions, default=0.0)
    entropy = -sum(proportion * math.log2(proportion) for proportion in proportions)
    return round(concentration, 8), round(entropy, 8)


def _validate_values(values: dict[str, FeatureScalar]) -> None:
    definitions = {definition.name: definition for definition in FEATURE_DEFINITIONS}
    if set(values) != set(definitions):
        raise ValueError("feature payload does not exactly match schema v1")
    for name, value in values.items():
        definition = definitions[name]
        if value is None:
            if not definition.nullable:
                raise ValueError(f"feature {name} cannot be null")
            continue
        if definition.value_type == "integer" and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
            raise ValueError(f"feature {name} must be an integer")
        if definition.value_type == "float" and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            raise ValueError(f"feature {name} must be a float")


def extract_feature_set(
    normalized_diff: NormalizedDiff,
    blast_radius: BlastRadius,
    history: HistoricalStatistics,
    *,
    commit_count: int | None,
) -> FeatureSet:
    if commit_count is not None and (commit_count < 1 or commit_count > 10_000):
        raise ValueError("commit_count must be between 1 and 10000")
    type_counts = Counter(file.file_type for file in normalized_diff.files)
    concentration, entropy = _distribution(normalized_diff)
    blast_complete = (
        blast_radius.available
        and not blast_radius.missing_changed_paths
        and not blast_radius.truncated
    )
    history_available = "repository_history" not in history.missing
    values: dict[str, FeatureScalar] = {
        "binary_files": type_counts["binary"],
        "blast_direct_modules": len(blast_radius.direct_modules) if blast_complete else None,
        "blast_impacted_tests": len(blast_radius.impacted_tests) if blast_complete else None,
        "blast_max_depth": blast_radius.max_depth if blast_complete else None,
        "blast_transitive_modules": (
            len(blast_radius.transitive_modules) if blast_complete else None
        ),
        "change_concentration": concentration,
        "change_entropy": entropy,
        "commit_count": commit_count,
        "deleted_files": sum(file.status == "removed" for file in normalized_diff.files),
        "dependency_files_changed": type_counts["dependency"],
        "files_changed": len(normalized_diff.files),
        "generated_files": type_counts["generated"],
        "historical_file_touches_90d": history.target_file_touches if history_available else None,
        "historical_line_churn_90d": history.line_churn if history_available else None,
        "historical_module_touches_90d": (
            history.target_module_touches if history_available else None
        ),
        "lines_added": sum(file.additions for file in normalized_diff.files),
        "lines_deleted": sum(file.deletions for file in normalized_diff.files),
        "migration_files_changed": type_counts["migration"],
        "ownership_familiarity_90d": history.ownership_familiarity,
        "prior_failure_proxy_count_90d": history.prior_failure_proxy_count,
        "python_files_changed": sum(file.language == "python" for file in normalized_diff.files),
        "renamed_files": sum(file.status == "renamed" for file in normalized_diff.files),
        "sensitive_files_changed": sum(bool(file.sensitive_tags) for file in normalized_diff.files),
        "test_files_changed": type_counts["test"],
        "vendored_files": type_counts["vendored"],
    }
    missing: dict[str, str] = {}
    if commit_count is None:
        missing["commit_count"] = "snapshot did not provide a bounded commit count"
    if not blast_complete:
        blast_reason = (
            "base source tree was unavailable for static graph analysis"
            if not blast_radius.available
            else "static graph coverage was partial or bounded"
        )
        for name in (
            "blast_direct_modules",
            "blast_impacted_tests",
            "blast_max_depth",
            "blast_transitive_modules",
        ):
            missing[name] = blast_reason
    if not history_available:
        for name in (
            "historical_file_touches_90d",
            "historical_line_churn_90d",
            "historical_module_touches_90d",
        ):
            missing[name] = "no repository history existed before prediction time"
    if history.prior_failure_proxy_count is None:
        missing["prior_failure_proxy_count_90d"] = "no pre-change check proxy observations"
    if history.ownership_familiarity is None:
        missing["ownership_familiarity_90d"] = "opaque author/history coverage unavailable"
    provenance = {definition.name: definition.source for definition in FEATURE_DEFINITIONS}
    _validate_values(values)
    payload = {
        "definitions": [definition.as_dict() for definition in FEATURE_DEFINITIONS],
        "extractor_version": EXTRACTOR_VERSION,
        "missing": dict(sorted(missing.items())),
        "provenance": dict(sorted(provenance.items())),
        "schema_version": FEATURE_SCHEMA_VERSION,
        "values": dict(sorted(values.items())),
    }
    return FeatureSet(
        schema_version=FEATURE_SCHEMA_VERSION,
        extractor_version=EXTRACTOR_VERSION,
        values=values,
        missing=missing,
        provenance=provenance,
        feature_hash=canonical_hash(payload),
    )


def render_risk_factors(
    normalized_diff: NormalizedDiff,
    blast_radius: BlastRadius,
    features: FeatureSet,
) -> tuple[RiskFactor, ...]:
    def title(prefix: str, value: str) -> str:
        combined = f"{prefix}{value}"
        return combined if len(combined) <= 256 else f"{combined[:253]}..."

    factors: list[RiskFactor] = []
    for definition in FEATURE_DEFINITIONS:
        value = features.values[definition.name]
        missing_reason = features.missing.get(definition.name)
        factors.append(
            RiskFactor(
                rule_id=f"{EVIDENCE_SCHEMA_VERSION}.feature.{definition.name}",
                title=definition.name.replace("_", " ").title(),
                value=value,
                reason=missing_reason or f"Deterministic value from {definition.source}.",
                source_refs=(definition.source,),
                missing=missing_reason is not None,
            )
        )
    for changed_file in normalized_diff.files:
        factors.append(
            RiskFactor(
                rule_id=f"{EVIDENCE_SCHEMA_VERSION}.changed_file",
                title=title("Changed file: ", changed_file.path),
                value={
                    "additions": changed_file.additions,
                    "deletions": changed_file.deletions,
                    "file_type": changed_file.file_type,
                    "language": changed_file.language,
                    "status": changed_file.status,
                },
                reason="Normalized immutable snapshot fact.",
                source_refs=(f"snapshot.changed_files:{changed_file.path}",),
            )
        )
    for path in blast_radius.evidence_paths:
        factors.append(
            RiskFactor(
                rule_id=f"{EVIDENCE_SCHEMA_VERSION}.blast_path",
                title=title("Affected module: ", path.affected_module),
                value=path.as_dict(),
                reason="Static reverse-import reachability; not a dynamic call graph.",
                source_refs=tuple(f"python_module:{module}" for module in path.modules),
            )
        )
    if blast_radius.missing_changed_paths:
        factors.append(
            RiskFactor(
                rule_id=f"{EVIDENCE_SCHEMA_VERSION}.graph_missing_paths",
                title="Files outside the supported Python graph",
                value={"paths": list(blast_radius.missing_changed_paths)},
                reason="No supported Python module node was available for these changed paths.",
                source_refs=tuple(
                    f"snapshot.changed_files:{path}" for path in blast_radius.missing_changed_paths
                ),
                missing=True,
            )
        )
    return tuple(factors)
