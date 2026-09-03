"""Outcome-blind semantic-dataset derivation over the frozen M4 split."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from packages.change_intel import canonical_hash
from packages.dataset_core.contracts import DatasetBuild, DatasetSplit, ExtractedSource

SEMANTIC_ANNOTATION_SCHEMA_VERSION = "semantic-annotation-v1"
SEMANTIC_DATASET_SCHEMA_VERSION = "semantic-dataset-v1"
SEMANTIC_TEXT_VERSION = "semantic-change-text-v1"
SEMANTIC_LEAKAGE_REPORT_VERSION = "semantic-leakage-report-v1"
MAX_SEMANTIC_TEXT_BYTES = 4_096
MAX_CATEGORIES = 16
MAX_ROWS = 10_000


class SemanticDatasetError(ValueError):
    """The semantic derivative violates provenance, bounds, or split invariants."""


def _bounded_string(value: object, *, field: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise SemanticDatasetError(f"{field} must be a bounded non-empty string")
    return value


def _string_list(value: object, *, field: str, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise SemanticDatasetError(f"{field} must be a bounded list")
    items = tuple(_bounded_string(item, field=field) for item in value)
    if len(set(items)) != len(items):
        raise SemanticDatasetError(f"{field} must not contain duplicates")
    return items


def _checksum(value: object, *, field: str) -> str:
    text = _bounded_string(value, field=field, maximum=64)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise SemanticDatasetError(f"{field} must be a lowercase SHA-256 checksum")
    return text


@dataclass(frozen=True, slots=True)
class SemanticAnnotationSet:
    dataset_version: str
    source_dataset_version: str
    source_manifest_sha256: str
    source_split_sha256: str
    source_admission_sha256: str
    annotation_rule_version: str
    annotator: str
    annotated_at: datetime
    outcome_blind: bool
    allowed_input_fields: tuple[str, ...]
    blinded_fields: tuple[str, ...]
    categories: tuple[str, ...]
    annotations: dict[str, tuple[str, ...]]
    license: str
    source_content_license: str
    usage: str
    annotation_sha256: str


@dataclass(frozen=True, slots=True)
class SemanticDatasetRow:
    snapshot_id: str
    repository_numeric_id: int
    split: DatasetSplit
    text: str
    text_sha256: str
    text_bytes: int
    text_truncated: bool
    categories: tuple[str, ...]
    label_vector: tuple[int, ...]
    row_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "categories": list(self.categories),
            "label_vector": list(self.label_vector),
            "repository_numeric_id": self.repository_numeric_id,
            "row_sha256": self.row_sha256,
            "snapshot_id": self.snapshot_id,
            "split": self.split,
            "text": self.text,
            "text_bytes": self.text_bytes,
            "text_sha256": self.text_sha256,
            "text_truncated": self.text_truncated,
        }


@dataclass(frozen=True, slots=True)
class SemanticDataset:
    dataset_version: str
    annotation_rule_version: str
    annotation_sha256: str
    source_dataset_version: str
    source_manifest_sha256: str
    source_split_sha256: str
    source_admission_sha256: str
    source_leakage_report_sha256: str
    text_version: str
    categories: tuple[str, ...]
    rows: tuple[SemanticDatasetRow, ...]
    counts: dict[str, object]
    leakage_report: dict[str, object]
    synthetic: bool
    license: str
    source_content_license: str
    usage: str
    manifest_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "manifest": {
                "annotation_rule_version": self.annotation_rule_version,
                "annotation_sha256": self.annotation_sha256,
                "categories": list(self.categories),
                "counts": self.counts,
                "dataset_version": self.dataset_version,
                "leakage_report": self.leakage_report,
                "license": self.license,
                "manifest_sha256": self.manifest_sha256,
                "schema_version": SEMANTIC_DATASET_SCHEMA_VERSION,
                "source_admission_sha256": self.source_admission_sha256,
                "source_content_license": self.source_content_license,
                "source_dataset_version": self.source_dataset_version,
                "source_leakage_report_sha256": self.source_leakage_report_sha256,
                "source_manifest_sha256": self.source_manifest_sha256,
                "source_split_sha256": self.source_split_sha256,
                "synthetic": self.synthetic,
                "text_version": self.text_version,
                "usage": self.usage,
            },
            "rows": [row.as_dict() for row in self.rows],
        }


def parse_semantic_annotations(payload: Mapping[str, object]) -> SemanticAnnotationSet:
    required = {
        "allowed_input_fields",
        "annotated_at",
        "annotation_rule_version",
        "annotations",
        "annotator",
        "blinded_fields",
        "categories",
        "dataset_version",
        "license",
        "outcome_blind",
        "schema_version",
        "source_admission_sha256",
        "source_content_license",
        "source_dataset_version",
        "source_manifest_sha256",
        "source_split_sha256",
        "usage",
    }
    if (
        set(payload) != required
        or payload.get("schema_version") != SEMANTIC_ANNOTATION_SCHEMA_VERSION
    ):
        raise SemanticDatasetError("semantic annotation must exactly match schema v1")
    if payload.get("outcome_blind") is not True:
        raise SemanticDatasetError("semantic annotations must be outcome blind")
    categories = _string_list(payload.get("categories"), field="categories", maximum=MAX_CATEGORIES)
    if not categories or tuple(sorted(categories)) != categories:
        raise SemanticDatasetError("semantic categories must be non-empty and sorted")
    allowed = _string_list(
        payload.get("allowed_input_fields"), field="allowed_input_fields", maximum=16
    )
    if allowed != (
        "changed_files.path",
        "changed_files.status",
        "changed_files.patch",
    ):
        raise SemanticDatasetError("semantic text fields must match the pre-outcome allowlist")
    blinded = _string_list(payload.get("blinded_fields"), field="blinded_fields", maximum=16)
    required_blinded = {
        "outcome.kind",
        "outcome.observed_at",
        "outcome.evidence_refs",
        "proxy_label",
    }
    if set(blinded) != required_blinded:
        raise SemanticDatasetError(
            "semantic annotation must blind all outcome and proxy-label fields"
        )
    raw_annotations = payload.get("annotations")
    if (
        not isinstance(raw_annotations, dict)
        or not raw_annotations
        or len(raw_annotations) > MAX_ROWS
        or not all(isinstance(key, str) for key in raw_annotations)
    ):
        raise SemanticDatasetError("semantic annotations must be a bounded object")
    annotations: dict[str, tuple[str, ...]] = {}
    for snapshot_id, raw_labels in raw_annotations.items():
        snapshot = _bounded_string(snapshot_id, field="annotation snapshot_id", maximum=128)
        labels = _string_list(raw_labels, field=f"annotations.{snapshot}", maximum=MAX_CATEGORIES)
        if not labels or tuple(sorted(labels)) != labels or not set(labels).issubset(categories):
            raise SemanticDatasetError(
                "semantic row labels must be sorted members of the vocabulary"
            )
        annotations[snapshot] = labels
    annotated_at_text = _bounded_string(
        payload.get("annotated_at"), field="annotated_at", maximum=64
    )
    try:
        annotated_at = datetime.fromisoformat(annotated_at_text.replace("Z", "+00:00"))
    except ValueError as error:
        raise SemanticDatasetError("annotated_at must be an ISO-8601 datetime") from error
    if annotated_at.utcoffset() is None:
        raise SemanticDatasetError("annotated_at must be timezone aware")
    annotation_payload = dict(payload)
    return SemanticAnnotationSet(
        dataset_version=_bounded_string(payload.get("dataset_version"), field="dataset_version"),
        source_dataset_version=_bounded_string(
            payload.get("source_dataset_version"), field="source_dataset_version"
        ),
        source_manifest_sha256=_checksum(
            payload.get("source_manifest_sha256"), field="source_manifest_sha256"
        ),
        source_split_sha256=_checksum(
            payload.get("source_split_sha256"), field="source_split_sha256"
        ),
        source_admission_sha256=_checksum(
            payload.get("source_admission_sha256"), field="source_admission_sha256"
        ),
        annotation_rule_version=_bounded_string(
            payload.get("annotation_rule_version"), field="annotation_rule_version"
        ),
        annotator=_bounded_string(payload.get("annotator"), field="annotator"),
        annotated_at=annotated_at,
        outcome_blind=True,
        allowed_input_fields=allowed,
        blinded_fields=blinded,
        categories=categories,
        annotations=annotations,
        license=_bounded_string(payload.get("license"), field="license", maximum=64),
        source_content_license=_bounded_string(
            payload.get("source_content_license"), field="source_content_license", maximum=64
        ),
        usage=_bounded_string(payload.get("usage"), field="usage", maximum=1_000),
        annotation_sha256=canonical_hash(annotation_payload),
    )


def _bounded_utf8(text: str) -> tuple[str, bool]:
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_SEMANTIC_TEXT_BYTES:
        return text, False
    bounded = encoded[:MAX_SEMANTIC_TEXT_BYTES]
    while bounded:
        try:
            return bounded.decode("utf-8"), True
        except UnicodeDecodeError:
            bounded = bounded[:-1]
    raise SemanticDatasetError("semantic text could not be bounded as UTF-8")


def _semantic_text(snapshot: object) -> tuple[str, bool]:
    changed_files = getattr(snapshot, "changed_files", None)
    if not isinstance(changed_files, tuple) or not changed_files:
        raise SemanticDatasetError("semantic rows require changed-file input")
    blocks: list[str] = []
    for changed_file in sorted(changed_files, key=lambda item: item.path):
        path = changed_file.path.replace("\\", "/")
        patch = (
            (changed_file.patch or "<patch unavailable>").replace("\r\n", "\n").replace("\r", "\n")
        )
        blocks.append(f"[FILE] {path}\n[STATUS] {changed_file.status}\n[PATCH]\n{patch}")
    return _bounded_utf8("\n\n".join(blocks))


def build_semantic_dataset(
    *,
    source_dataset: DatasetBuild,
    extracted_source: ExtractedSource,
    annotations: SemanticAnnotationSet,
) -> SemanticDataset:
    """Build a separate semantic dataset without reading any outcome field."""
    manifest = source_dataset.manifest
    if not manifest.synthetic or not extracted_source.admission.synthetic:
        raise SemanticDatasetError(
            "M11 fixture evaluation accepts only the admitted synthetic source"
        )
    if manifest.leakage_report.violations:
        raise SemanticDatasetError("source leakage report must pass before semantic derivation")
    if (
        annotations.source_dataset_version != manifest.dataset_version
        or annotations.source_manifest_sha256 != manifest.manifest_hash
        or annotations.source_split_sha256 != manifest.split_hash
        or annotations.source_admission_sha256 != extracted_source.admission.admission_hash
        or extracted_source.admission.source_id not in manifest.source_payload_hashes
    ):
        raise SemanticDatasetError("semantic annotations do not match the frozen source lineage")
    source_rows = {row.snapshot_id: row for row in source_dataset.rows}
    source_snapshots = {row.snapshot_id: row for row in extracted_source.records}
    expected_ids = set(source_rows)
    if set(source_snapshots) != expected_ids or set(annotations.annotations) != expected_ids:
        raise SemanticDatasetError(
            "semantic rows, source snapshots, and annotations must align exactly"
        )

    rows: list[SemanticDatasetRow] = []
    seen_by_split: dict[str, DatasetSplit] = {}
    for snapshot_id in sorted(expected_ids):
        source_row = source_rows[snapshot_id]
        text, truncated = _semantic_text(source_snapshots[snapshot_id])
        text_sha256 = canonical_hash({"text": text, "text_version": SEMANTIC_TEXT_VERSION})
        prior_split = seen_by_split.get(text_sha256)
        if prior_split is not None and prior_split is not source_row.split:
            raise SemanticDatasetError("exact semantic text cannot cross frozen split boundaries")
        seen_by_split[text_sha256] = source_row.split
        labels = annotations.annotations[snapshot_id]
        label_vector = tuple(int(category in labels) for category in annotations.categories)
        row_payload = {
            "categories": list(labels),
            "label_vector": list(label_vector),
            "repository_numeric_id": source_row.repository_numeric_id,
            "snapshot_id": snapshot_id,
            "source_row_sha256": source_row.row_hash,
            "split": source_row.split,
            "text_bytes": len(text.encode("utf-8")),
            "text_sha256": text_sha256,
            "text_truncated": truncated,
            "text_version": SEMANTIC_TEXT_VERSION,
        }
        rows.append(
            SemanticDatasetRow(
                snapshot_id=snapshot_id,
                repository_numeric_id=source_row.repository_numeric_id,
                split=source_row.split,
                text=text,
                text_sha256=text_sha256,
                text_bytes=len(text.encode("utf-8")),
                text_truncated=truncated,
                categories=labels,
                label_vector=label_vector,
                row_sha256=canonical_hash(row_payload),
            )
        )
    split_counts = Counter(row.split.value for row in rows)
    included = [row for row in rows if row.split is not DatasetSplit.EXCLUDED]
    category_counts = {
        category: sum(category in row.categories for row in included)
        for category in annotations.categories
    }
    repository_counts = Counter(row.repository_numeric_id for row in included)
    counts: dict[str, object] = {
        "category_positive_counts": category_counts,
        "included_rows": len(included),
        "repository_counts": {str(key): value for key, value in sorted(repository_counts.items())},
        "split_counts": dict(sorted(split_counts.items())),
        "total_rows": len(rows),
        "truncated_rows": sum(row.text_truncated for row in rows),
    }
    leakage_payload: dict[str, object] = {
        "limitations": [
            "The fixture contains one repository, so repository-holdout behavior is not measured.",
            "Outcome-blind synthetic category annotations validate the pipeline, not real label "
            "quality.",
        ],
        "passed_checks": [
            "source_m4_leakage_report_passed",
            "outcome_and_proxy_fields_blinded",
            "pre_outcome_text_field_allowlist_exact",
            "frozen_m4_split_inherited",
            "all_source_rows_covered_once",
            "no_exact_text_across_splits",
        ],
        "repository_holdout_measured": len(repository_counts) > 1,
        "schema_version": SEMANTIC_LEAKAGE_REPORT_VERSION,
        "source_report_sha256": manifest.leakage_report.report_hash,
        "violations": [],
    }
    leakage_report = {
        **leakage_payload,
        "report_sha256": canonical_hash(leakage_payload),
    }
    manifest_payload: dict[str, object] = {
        "annotation_rule_version": annotations.annotation_rule_version,
        "annotation_sha256": annotations.annotation_sha256,
        "categories": list(annotations.categories),
        "counts": counts,
        "dataset_version": annotations.dataset_version,
        "leakage_report": leakage_report,
        "license": annotations.license,
        "schema_version": SEMANTIC_DATASET_SCHEMA_VERSION,
        "source_admission_sha256": annotations.source_admission_sha256,
        "source_content_license": annotations.source_content_license,
        "source_dataset_version": annotations.source_dataset_version,
        "source_leakage_report_sha256": manifest.leakage_report.report_hash,
        "source_manifest_sha256": annotations.source_manifest_sha256,
        "source_split_sha256": annotations.source_split_sha256,
        "synthetic": True,
        "text_version": SEMANTIC_TEXT_VERSION,
        "usage": annotations.usage,
    }
    return SemanticDataset(
        dataset_version=annotations.dataset_version,
        annotation_rule_version=annotations.annotation_rule_version,
        annotation_sha256=annotations.annotation_sha256,
        source_dataset_version=annotations.source_dataset_version,
        source_manifest_sha256=annotations.source_manifest_sha256,
        source_split_sha256=annotations.source_split_sha256,
        source_admission_sha256=annotations.source_admission_sha256,
        source_leakage_report_sha256=manifest.leakage_report.report_hash,
        text_version=SEMANTIC_TEXT_VERSION,
        categories=annotations.categories,
        rows=tuple(rows),
        counts=counts,
        leakage_report=leakage_report,
        synthetic=True,
        license=annotations.license,
        source_content_license=annotations.source_content_license,
        usage=annotations.usage,
        manifest_sha256=canonical_hash(manifest_payload),
    )
