"""Versioned, framework-light contracts for dataset provenance and evaluation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from packages.change_intel import RawChangedFile, canonical_hash
from packages.change_intel.contracts import FeatureScalar

SOURCE_ADMISSION_SCHEMA_VERSION = "source-admission-v1"
EXTRACTION_SCHEMA_VERSION = "fixture-extraction-v1"
LABEL_RULE_VERSION = "proxy-label-rule-v1"
SPLIT_RULE_VERSION = "temporal-split-v1"
MATERIALIZATION_VERSION = "feature-materialization-v1"
DATASET_MANIFEST_SCHEMA_VERSION = "dataset-manifest-v1"

_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_CHECKSUM_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def require_aware(value: datetime, *, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def require_sha(value: str, *, field: str) -> None:
    if _SHA_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase 40-character commit SHA")


def require_checksum(value: str, *, field: str) -> None:
    if _CHECKSUM_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 checksum")


class SourceKind(StrEnum):
    FIXTURE = "fixture"
    PUBLIC_REPOSITORY = "public_repository"


class AcquisitionMethod(StrEnum):
    FIXTURE_BUNDLE = "fixture_bundle"
    GITHUB_API = "github_api"


class ProxyOutcomeKind(StrEnum):
    EXPLICIT_REVERT = "explicit_revert"
    HOTFIX = "hotfix"
    RAPID_FOLLOWUP_FIX = "rapid_followup_fix"
    FAILED_REQUIRED_CHECK = "failed_required_check"
    NO_PROXY_OBSERVED = "no_proxy_observed"
    AMBIGUOUS = "ambiguous"


class ProxyLabel(StrEnum):
    POSITIVE = "proxy_positive"
    NEGATIVE = "proxy_negative"
    UNKNOWN = "unknown"


class DatasetSplit(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"
    EXCLUDED = "excluded"


@dataclass(frozen=True, slots=True)
class SourceAdmission:
    source_id: str
    source_kind: SourceKind
    repository_numeric_id: int
    canonical_url: str
    license_spdx: str
    license_evidence_sha256: str
    license_version: str
    terms_url: str
    terms_reviewed_at: datetime
    acquisition_method: AcquisitionMethod
    allowed_fields: tuple[str, ...]
    allowed_artifacts: tuple[str, ...]
    redistribution_allowed: bool
    redistribution_notes: str
    retention_days: int | None
    attribution: str
    as_of: datetime
    observation_window_days: int
    reviewer: str
    approved: bool
    synthetic: bool
    max_records: int
    rate_limit_per_hour: int | None
    schema_version: str = SOURCE_ADMISSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SOURCE_ADMISSION_SCHEMA_VERSION:
            raise ValueError("source admission schema is incompatible")
        if not self.source_id or len(self.source_id) > 128:
            raise ValueError("source_id must be bounded")
        if self.repository_numeric_id < 1:
            raise ValueError("repository_numeric_id must be positive")
        if self.source_kind is SourceKind.PUBLIC_REPOSITORY and not self.canonical_url.startswith(
            "https://github.com/"
        ):
            raise ValueError("public sources require a canonical GitHub HTTPS URL")
        if self.source_kind is SourceKind.FIXTURE and not self.canonical_url.startswith(
            "fixture://"
        ):
            raise ValueError("fixture sources require a fixture URL")
        if not self.license_spdx or not self.license_version:
            raise ValueError("license identity and version are required")
        require_checksum(self.license_evidence_sha256, field="license evidence")
        if not self.terms_url or not self.reviewer:
            raise ValueError("terms evidence and reviewer are required")
        require_aware(self.terms_reviewed_at, field="terms_reviewed_at")
        require_aware(self.as_of, field="as_of")
        if not self.allowed_fields or not self.allowed_artifacts:
            raise ValueError("allowed fields and artifacts cannot be empty")
        if len(set(self.allowed_fields)) != len(self.allowed_fields):
            raise ValueError("allowed fields must be unique")
        if self.retention_days is not None and self.retention_days < 1:
            raise ValueError("retention_days must be positive when present")
        if self.observation_window_days < 1 or self.observation_window_days > 365:
            raise ValueError("observation window must be between 1 and 365 days")
        if self.max_records < 1 or self.max_records > 100_000:
            raise ValueError("max_records must be between 1 and 100000")
        if self.rate_limit_per_hour is not None and self.rate_limit_per_hour < 1:
            raise ValueError("rate limit must be positive when present")
        if self.source_kind is SourceKind.PUBLIC_REPOSITORY:
            if self.synthetic:
                raise ValueError("public source cannot be marked synthetic")
            if self.acquisition_method is not AcquisitionMethod.GITHUB_API:
                raise ValueError("public source acquisition must use the approved API")
            if self.rate_limit_per_hour is None:
                raise ValueError("public API admission requires a rate limit")
        elif self.acquisition_method is not AcquisitionMethod.FIXTURE_BUNDLE:
            raise ValueError("fixture source acquisition must use the fixture bundle")

    @property
    def admission_hash(self) -> str:
        return canonical_hash(self.as_dict(include_hash=False))

    def as_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "acquisition_method": self.acquisition_method,
            "allowed_artifacts": list(self.allowed_artifacts),
            "allowed_fields": list(self.allowed_fields),
            "approved": self.approved,
            "as_of": self.as_of.isoformat(),
            "attribution": self.attribution,
            "canonical_url": self.canonical_url,
            "license_evidence_sha256": self.license_evidence_sha256,
            "license_spdx": self.license_spdx,
            "license_version": self.license_version,
            "max_records": self.max_records,
            "observation_window_days": self.observation_window_days,
            "rate_limit_per_hour": self.rate_limit_per_hour,
            "redistribution_allowed": self.redistribution_allowed,
            "redistribution_notes": self.redistribution_notes,
            "repository_numeric_id": self.repository_numeric_id,
            "retention_days": self.retention_days,
            "reviewer": self.reviewer,
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "synthetic": self.synthetic,
            "terms_reviewed_at": self.terms_reviewed_at.isoformat(),
            "terms_url": self.terms_url,
        }
        if include_hash:
            value["admission_hash"] = self.admission_hash
        return value


@dataclass(frozen=True, slots=True)
class OutcomeObservation:
    kind: ProxyOutcomeKind
    observed_at: datetime | None
    evidence_refs: tuple[str, ...]
    note: str


@dataclass(frozen=True, slots=True)
class ExtractedSnapshot:
    source_id: str
    snapshot_id: str
    repository_numeric_id: int
    prediction_time: datetime
    base_sha: str
    head_sha: str
    changed_files: tuple[RawChangedFile, ...]
    commit_count: int | None
    outcome: OutcomeObservation | None
    snapshot_hash: str


@dataclass(frozen=True, slots=True)
class ExtractedSource:
    admission: SourceAdmission
    payload_hash: str
    records: tuple[ExtractedSnapshot, ...]


@dataclass(frozen=True, slots=True)
class LabelAssignment:
    label: ProxyLabel
    rule_id: str
    reason: str
    outcome_kind: ProxyOutcomeKind | None
    observed_at: datetime | None
    evidence_refs: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "evidence_refs": list(self.evidence_refs),
            "label": self.label,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "outcome_kind": self.outcome_kind,
            "reason": self.reason,
            "rule_id": self.rule_id,
        }


@dataclass(frozen=True, slots=True)
class MaterializedFeatureRow:
    snapshot_id: str
    source_id: str
    repository_numeric_id: int
    prediction_time: datetime
    head_sha: str
    snapshot_hash: str
    diff_hash: str
    near_duplicate_hash: str
    feature_schema_version: str
    extractor_version: str
    feature_values: dict[str, FeatureScalar]
    feature_missing: dict[str, str]
    feature_provenance: dict[str, str]
    feature_hash: str
    label: LabelAssignment
    split: DatasetSplit
    row_hash: str

    def as_dict(self) -> dict[str, object]:
        return {
            "diff_hash": self.diff_hash,
            "extractor_version": self.extractor_version,
            "feature_hash": self.feature_hash,
            "feature_missing": dict(sorted(self.feature_missing.items())),
            "feature_provenance": dict(sorted(self.feature_provenance.items())),
            "feature_schema_version": self.feature_schema_version,
            "feature_values": dict(sorted(self.feature_values.items())),
            "head_sha": self.head_sha,
            "label": self.label.as_dict(),
            "near_duplicate_hash": self.near_duplicate_hash,
            "prediction_time": self.prediction_time.isoformat(),
            "repository_numeric_id": self.repository_numeric_id,
            "row_hash": self.row_hash,
            "snapshot_hash": self.snapshot_hash,
            "snapshot_id": self.snapshot_id,
            "source_id": self.source_id,
            "split": self.split,
        }


@dataclass(frozen=True, slots=True)
class LeakageReport:
    schema_version: str
    passed_checks: tuple[str, ...]
    violations: tuple[str, ...]
    report_hash: str

    def as_dict(self) -> dict[str, object]:
        return {
            "passed_checks": list(self.passed_checks),
            "report_hash": self.report_hash,
            "schema_version": self.schema_version,
            "violations": list(self.violations),
        }


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_version: str
    extraction_code_commit: str
    extraction_version: str
    source_admissions: tuple[SourceAdmission, ...]
    source_payload_hashes: dict[str, str]
    label_rule_version: str
    feature_schema_version: str
    feature_extractor_version: str
    split_rule_version: str
    split_policy: dict[str, object]
    split_assignments: dict[str, str]
    split_hash: str
    exclusions: dict[str, str]
    counts: dict[str, object]
    leakage_report: LeakageReport
    synthetic: bool
    usage_notes: str
    license_notes: str
    known_label_weaknesses: tuple[str, ...]
    lineage: dict[str, str]
    manifest_hash: str
    schema_version: str = DATASET_MANIFEST_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "counts": self.counts,
            "dataset_version": self.dataset_version,
            "exclusions": dict(sorted(self.exclusions.items())),
            "extraction_code_commit": self.extraction_code_commit,
            "extraction_version": self.extraction_version,
            "feature_extractor_version": self.feature_extractor_version,
            "feature_schema_version": self.feature_schema_version,
            "known_label_weaknesses": list(self.known_label_weaknesses),
            "label_rule_version": self.label_rule_version,
            "leakage_report": self.leakage_report.as_dict(),
            "license_notes": self.license_notes,
            "lineage": dict(sorted(self.lineage.items())),
            "manifest_hash": self.manifest_hash,
            "schema_version": self.schema_version,
            "source_admissions": [item.as_dict() for item in self.source_admissions],
            "source_payload_hashes": dict(sorted(self.source_payload_hashes.items())),
            "split_assignments": dict(sorted(self.split_assignments.items())),
            "split_hash": self.split_hash,
            "split_policy": self.split_policy,
            "split_rule_version": self.split_rule_version,
            "synthetic": self.synthetic,
            "usage_notes": self.usage_notes,
        }


@dataclass(frozen=True, slots=True)
class DatasetBuild:
    manifest: DatasetManifest
    rows: tuple[MaterializedFeatureRow, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "manifest": self.manifest.as_dict(),
            "rows": [row.as_dict() for row in self.rows],
        }
