"""Reproducible feature materialization from admitted immutable snapshots."""

from __future__ import annotations

import re
from collections import Counter

from packages.change_intel import (
    EXTRACTOR_VERSION,
    FEATURE_SCHEMA_VERSION,
    ChangeIntelligenceResult,
    analyze_change,
    canonical_hash,
)
from packages.dataset_core.contracts import (
    DATASET_MANIFEST_SCHEMA_VERSION,
    EXTRACTION_SCHEMA_VERSION,
    LABEL_RULE_VERSION,
    MATERIALIZATION_VERSION,
    DatasetBuild,
    DatasetManifest,
    DatasetSplit,
    ExtractedSource,
    MaterializedFeatureRow,
    ProxyLabel,
    require_sha,
)
from packages.dataset_core.labels import KNOWN_LABEL_WEAKNESSES, assign_proxy_label
from packages.dataset_core.splits import (
    TemporalSplitPolicy,
    run_leakage_checks,
    split_assignment_hash,
)

_NEAR_DUPLICATE_TOKEN = re.compile(r"[A-Za-z_]+|\d+|[^\w\s]", re.UNICODE)


def _near_duplicate_hash(result: ChangeIntelligenceResult) -> str:
    files = result.normalized_diff.files
    skeleton: list[dict[str, object]] = []
    for changed_file in files:
        patch = changed_file.patch or ""
        tokens = [
            "<number>" if token.isdigit() else token.casefold()
            for token in _NEAR_DUPLICATE_TOKEN.findall(patch)
        ]
        skeleton.append(
            {
                "file_type": changed_file.file_type,
                "language": changed_file.language,
                "patch_tokens": tokens,
                "status": changed_file.status,
            }
        )
    return canonical_hash({"algorithm": "patch-token-skeleton-v1", "files": skeleton})


def _materialized_row(
    *,
    source: ExtractedSource,
    record_index: int,
    policy: TemporalSplitPolicy,
) -> MaterializedFeatureRow:
    snapshot = source.records[record_index]
    result = analyze_change(
        changed_files=snapshot.changed_files,
        prediction_time=snapshot.prediction_time,
        history=(),
        source_tree=None,
        current_author_key=None,
        commit_count=snapshot.commit_count,
    )
    label = assign_proxy_label(snapshot, admission=source.admission)
    split = policy.assign(prediction_time=snapshot.prediction_time, label=label.label)
    row_payload = {
        "diff_hash": result.normalized_diff.diff_hash,
        "extractor_version": result.features.extractor_version,
        "feature_hash": result.features.feature_hash,
        "feature_missing": result.features.missing,
        "feature_provenance": result.features.provenance,
        "feature_schema_version": result.features.schema_version,
        "feature_values": result.features.values,
        "head_sha": snapshot.head_sha,
        "label": label.as_dict(),
        "materialization_version": MATERIALIZATION_VERSION,
        "near_duplicate_hash": _near_duplicate_hash(result),
        "prediction_time": snapshot.prediction_time.isoformat(),
        "repository_numeric_id": snapshot.repository_numeric_id,
        "snapshot_hash": snapshot.snapshot_hash,
        "snapshot_id": snapshot.snapshot_id,
        "source_id": snapshot.source_id,
        "split": split,
    }
    return MaterializedFeatureRow(
        snapshot_id=snapshot.snapshot_id,
        source_id=snapshot.source_id,
        repository_numeric_id=snapshot.repository_numeric_id,
        prediction_time=snapshot.prediction_time,
        head_sha=snapshot.head_sha,
        snapshot_hash=snapshot.snapshot_hash,
        diff_hash=result.normalized_diff.diff_hash,
        near_duplicate_hash=str(row_payload["near_duplicate_hash"]),
        feature_schema_version=result.features.schema_version,
        extractor_version=result.features.extractor_version,
        feature_values=result.features.values,
        feature_missing=result.features.missing,
        feature_provenance=result.features.provenance,
        feature_hash=result.features.feature_hash,
        label=label,
        split=split,
        row_hash=canonical_hash(row_payload),
    )


def build_dataset(
    *,
    dataset_version: str,
    source: ExtractedSource,
    split_policy: TemporalSplitPolicy,
    extraction_code_commit: str,
) -> DatasetBuild:
    if not dataset_version or len(dataset_version) > 128:
        raise ValueError("dataset_version must be bounded")
    require_sha(extraction_code_commit, field="extraction_code_commit")
    rows = tuple(
        _materialized_row(source=source, record_index=index, policy=split_policy)
        for index in range(len(source.records))
    )
    leakage_report = run_leakage_checks(rows, policy=split_policy)
    assignments = {row.snapshot_id: row.split.value for row in rows}
    split_hash = split_assignment_hash(rows)
    exclusions = {
        row.snapshot_id: row.label.reason for row in rows if row.split is DatasetSplit.EXCLUDED
    }
    split_counts = Counter(row.split.value for row in rows)
    label_counts = Counter(row.label.label.value for row in rows)
    included = [row for row in rows if row.split is not DatasetSplit.EXCLUDED]
    positive_count = sum(row.label.label is ProxyLabel.POSITIVE for row in included)
    counts: dict[str, object] = {
        "class_balance": dict(sorted(label_counts.items())),
        "included_rows": len(included),
        "positive_prevalence": round(positive_count / len(included), 8) if included else None,
        "split_counts": dict(sorted(split_counts.items())),
        "total_rows": len(rows),
        "unknown_rows": label_counts[ProxyLabel.UNKNOWN.value],
    }
    lineage = {
        "admission_hash": source.admission.admission_hash,
        "extraction_code_commit": extraction_code_commit,
        "feature_extractor_version": EXTRACTOR_VERSION,
        "source_payload_hash": source.payload_hash,
    }
    manifest_payload = {
        "counts": counts,
        "dataset_version": dataset_version,
        "exclusions": dict(sorted(exclusions.items())),
        "extraction_code_commit": extraction_code_commit,
        "extraction_version": EXTRACTION_SCHEMA_VERSION,
        "feature_extractor_version": EXTRACTOR_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "known_label_weaknesses": list(KNOWN_LABEL_WEAKNESSES),
        "label_rule_version": LABEL_RULE_VERSION,
        "leakage_report": leakage_report.as_dict(),
        "license_notes": (
            f"{source.admission.license_spdx} evidence {source.admission.license_evidence_sha256}; "
            f"redistribution_allowed={source.admission.redistribution_allowed}."
        ),
        "lineage": lineage,
        "schema_version": DATASET_MANIFEST_SCHEMA_VERSION,
        "source_admissions": [source.admission.as_dict()],
        "source_payload_hashes": {source.admission.source_id: source.payload_hash},
        "split_assignments": dict(sorted(assignments.items())),
        "split_hash": split_hash,
        "split_policy": split_policy.as_dict(),
        "split_rule_version": split_policy.version,
        "synthetic": source.admission.synthetic,
        "usage_notes": (
            "Synthetic fixture evaluation for pipeline and heuristic behavior only; not a "
            "customer, incident, accuracy, or production-performance claim."
        ),
    }
    manifest = DatasetManifest(
        dataset_version=dataset_version,
        extraction_code_commit=extraction_code_commit,
        extraction_version=EXTRACTION_SCHEMA_VERSION,
        source_admissions=(source.admission,),
        source_payload_hashes={source.admission.source_id: source.payload_hash},
        label_rule_version=LABEL_RULE_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        feature_extractor_version=EXTRACTOR_VERSION,
        split_rule_version=split_policy.version,
        split_policy=split_policy.as_dict(),
        split_assignments=assignments,
        split_hash=split_hash,
        exclusions=exclusions,
        counts=counts,
        leakage_report=leakage_report,
        synthetic=source.admission.synthetic,
        usage_notes=str(manifest_payload["usage_notes"]),
        license_notes=str(manifest_payload["license_notes"]),
        known_label_weaknesses=KNOWN_LABEL_WEAKNESSES,
        lineage=lineage,
        manifest_hash=canonical_hash(manifest_payload),
    )
    return DatasetBuild(manifest=manifest, rows=rows)
