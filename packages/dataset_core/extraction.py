"""Fail-closed parsing for approved fixture/public dataset inputs.

This module accepts already acquired inert records. It deliberately contains no HTTP client or
repository-mining behavior; a future public adapter must still obey the admission record.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from packages.change_intel import RawChangedFile, canonical_hash
from packages.dataset_core.contracts import (
    EXTRACTION_SCHEMA_VERSION,
    AcquisitionMethod,
    ExtractedSnapshot,
    ExtractedSource,
    OutcomeObservation,
    ProxyOutcomeKind,
    SourceAdmission,
    SourceKind,
    require_aware,
    require_sha,
)

MAX_CHANGED_FILES_PER_SNAPSHOT = 1_000
MAX_TOTAL_RECORDS = 100_000
MAX_EVIDENCE_REFS = 32
_RECORD_FIELDS = {
    "base_sha",
    "changed_files",
    "commit_count",
    "head_sha",
    "outcome",
    "prediction_time",
    "repository_numeric_id",
    "snapshot_id",
}
_CHANGED_FILE_FIELDS = {
    "additions",
    "deletions",
    "patch",
    "path",
    "previous_path",
    "status",
}
_OUTCOME_FIELDS = {"evidence_refs", "kind", "note", "observed_at"}


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return value


def _list(value: object, *, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def _string(value: object, *, field: str, maximum: int = 1_200) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{field} must be a bounded non-empty string")
    return value


def _integer(value: object, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer at least {minimum}")
    return value


def _optional_integer(value: object, *, field: str, minimum: int = 0) -> int | None:
    if value is None:
        return None
    return _integer(value, field=field, minimum=minimum)


def _datetime(value: object, *, field: str) -> datetime:
    text = _string(value, field=field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO-8601 datetime") from error
    require_aware(parsed, field=field)
    return parsed


def _optional_datetime(value: object, *, field: str) -> datetime | None:
    return None if value is None else _datetime(value, field=field)


def _string_tuple(value: object, *, field: str, maximum: int) -> tuple[str, ...]:
    values = _list(value, field=field)
    if len(values) > maximum:
        raise ValueError(f"{field} exceeds its item limit")
    result = tuple(_string(item, field=field) for item in values)
    if len(set(result)) != len(result):
        raise ValueError(f"{field} cannot contain duplicates")
    return result


def parse_source_admission(payload: Mapping[str, object]) -> SourceAdmission:
    """Parse the complete source-admission boundary without permissive coercion."""

    required = {
        "acquisition_method",
        "allowed_artifacts",
        "allowed_fields",
        "approved",
        "as_of",
        "attribution",
        "canonical_url",
        "license_evidence_sha256",
        "license_spdx",
        "license_version",
        "max_records",
        "observation_window_days",
        "rate_limit_per_hour",
        "redistribution_allowed",
        "redistribution_notes",
        "repository_numeric_id",
        "retention_days",
        "reviewer",
        "schema_version",
        "source_id",
        "source_kind",
        "synthetic",
        "terms_reviewed_at",
        "terms_url",
    }
    if set(payload) != required:
        raise ValueError("source admission must exactly match schema v1")
    if not isinstance(payload["approved"], bool) or not isinstance(
        payload["redistribution_allowed"], bool
    ):
        raise ValueError("admission approval and redistribution flags must be booleans")
    if not isinstance(payload["synthetic"], bool):
        raise ValueError("admission synthetic flag must be boolean")
    try:
        source_kind = SourceKind(_string(payload["source_kind"], field="source_kind"))
        acquisition_method = AcquisitionMethod(
            _string(payload["acquisition_method"], field="acquisition_method")
        )
    except ValueError as error:
        raise ValueError("source kind or acquisition method is unsupported") from error
    return SourceAdmission(
        source_id=_string(payload["source_id"], field="source_id", maximum=128),
        source_kind=source_kind,
        repository_numeric_id=_integer(
            payload["repository_numeric_id"], field="repository_numeric_id", minimum=1
        ),
        canonical_url=_string(payload["canonical_url"], field="canonical_url"),
        license_spdx=_string(payload["license_spdx"], field="license_spdx", maximum=64),
        license_evidence_sha256=_string(
            payload["license_evidence_sha256"], field="license_evidence_sha256", maximum=64
        ),
        license_version=_string(payload["license_version"], field="license_version"),
        terms_url=_string(payload["terms_url"], field="terms_url"),
        terms_reviewed_at=_datetime(payload["terms_reviewed_at"], field="terms_reviewed_at"),
        acquisition_method=acquisition_method,
        allowed_fields=_string_tuple(payload["allowed_fields"], field="allowed_fields", maximum=64),
        allowed_artifacts=_string_tuple(
            payload["allowed_artifacts"], field="allowed_artifacts", maximum=64
        ),
        redistribution_allowed=payload["redistribution_allowed"],
        redistribution_notes=_string(payload["redistribution_notes"], field="redistribution_notes"),
        retention_days=_optional_integer(
            payload["retention_days"], field="retention_days", minimum=1
        ),
        attribution=_string(payload["attribution"], field="attribution"),
        as_of=_datetime(payload["as_of"], field="as_of"),
        observation_window_days=_integer(
            payload["observation_window_days"], field="observation_window_days", minimum=1
        ),
        reviewer=_string(payload["reviewer"], field="reviewer"),
        approved=payload["approved"],
        synthetic=payload["synthetic"],
        max_records=_integer(payload["max_records"], field="max_records", minimum=1),
        rate_limit_per_hour=_optional_integer(
            payload["rate_limit_per_hour"], field="rate_limit_per_hour", minimum=1
        ),
        schema_version=_string(payload["schema_version"], field="schema_version", maximum=64),
    )


def _changed_file(value: object) -> RawChangedFile:
    item = _mapping(value, field="changed file")
    if set(item) != _CHANGED_FILE_FIELDS:
        raise ValueError("changed file must exactly match its extraction schema")
    patch_value = item["patch"]
    previous_path_value = item["previous_path"]
    if patch_value is not None and not isinstance(patch_value, str):
        raise ValueError("changed file patch must be text or null")
    if previous_path_value is not None and not isinstance(previous_path_value, str):
        raise ValueError("previous path must be text or null")
    return RawChangedFile(
        path=_string(item["path"], field="changed file path"),
        additions=_integer(item["additions"], field="additions"),
        deletions=_integer(item["deletions"], field="deletions"),
        status=_string(item["status"], field="status", maximum=32),
        previous_path=previous_path_value,
        patch=patch_value,
    )


def _outcome(value: object) -> OutcomeObservation | None:
    if value is None:
        return None
    item = _mapping(value, field="outcome")
    if set(item) != _OUTCOME_FIELDS:
        raise ValueError("outcome must exactly match its extraction schema")
    try:
        kind = ProxyOutcomeKind(_string(item["kind"], field="outcome kind", maximum=64))
    except ValueError as error:
        raise ValueError("outcome kind is unsupported") from error
    return OutcomeObservation(
        kind=kind,
        observed_at=_optional_datetime(item["observed_at"], field="outcome observed_at"),
        evidence_refs=_string_tuple(
            item["evidence_refs"], field="outcome evidence_refs", maximum=MAX_EVIDENCE_REFS
        ),
        note=_string(item["note"], field="outcome note"),
    )


def extract_approved_source(
    *, admission: SourceAdmission, payload: Mapping[str, object]
) -> ExtractedSource:
    if not admission.approved:
        raise PermissionError("source admission is not approved")
    if "feature_rows" not in admission.allowed_artifacts:
        raise PermissionError("source admission does not permit feature materialization")
    if admission.source_kind is SourceKind.PUBLIC_REPOSITORY:
        if admission.retention_days is None:
            raise PermissionError("public source admission must declare a retention limit")
        if not admission.redistribution_notes:
            raise PermissionError("public source admission must declare redistribution limits")
    if set(payload) != {"records", "schema_version", "source_id"}:
        raise ValueError("source payload must exactly match extraction schema v1")
    if payload["schema_version"] != EXTRACTION_SCHEMA_VERSION:
        raise ValueError("source payload extraction schema is incompatible")
    if payload["source_id"] != admission.source_id:
        raise ValueError("source payload does not match its admission record")
    if not _RECORD_FIELDS.issubset(set(admission.allowed_fields)):
        raise PermissionError("source admission does not allow every required snapshot field")
    raw_records = _list(payload["records"], field="records")
    limit = min(MAX_TOTAL_RECORDS, admission.max_records)
    if admission.rate_limit_per_hour is not None:
        limit = min(limit, admission.rate_limit_per_hour)
    if len(raw_records) > limit:
        raise ValueError("source record count exceeds its admission limit")

    records: list[ExtractedSnapshot] = []
    seen_snapshot_ids: set[str] = set()
    for raw_record in raw_records:
        record = _mapping(raw_record, field="record")
        if set(record) != _RECORD_FIELDS:
            raise ValueError("source record must exactly match extraction schema v1")
        snapshot_id = _string(record["snapshot_id"], field="snapshot_id", maximum=128)
        if snapshot_id in seen_snapshot_ids:
            raise ValueError("snapshot IDs must be unique within a source")
        seen_snapshot_ids.add(snapshot_id)
        repository_id = _integer(
            record["repository_numeric_id"], field="repository_numeric_id", minimum=1
        )
        if repository_id != admission.repository_numeric_id:
            raise ValueError("snapshot repository identity does not match admission")
        prediction_time = _datetime(record["prediction_time"], field="prediction_time")
        if prediction_time > admission.as_of:
            raise ValueError("snapshot prediction time exceeds the admitted as_of cutoff")
        base_sha = _string(record["base_sha"], field="base_sha", maximum=40)
        head_sha = _string(record["head_sha"], field="head_sha", maximum=40)
        require_sha(base_sha, field="base_sha")
        require_sha(head_sha, field="head_sha")
        changed_files = tuple(
            _changed_file(item) for item in _list(record["changed_files"], field="changed_files")
        )
        if len(changed_files) > MAX_CHANGED_FILES_PER_SNAPSHOT:
            raise ValueError("snapshot changed-file count exceeds the extraction limit")
        commit_count = _optional_integer(record["commit_count"], field="commit_count", minimum=1)
        if commit_count is not None and commit_count > 10_000:
            raise ValueError("commit_count exceeds the feature contract")
        snapshot_payload = {
            "base_sha": base_sha,
            "changed_files": [
                {
                    "additions": item.additions,
                    "deletions": item.deletions,
                    "patch": item.patch,
                    "path": item.path,
                    "previous_path": item.previous_path,
                    "status": item.status,
                }
                for item in changed_files
            ],
            "commit_count": commit_count,
            "head_sha": head_sha,
            "prediction_time": prediction_time.isoformat(),
            "repository_numeric_id": repository_id,
            "snapshot_id": snapshot_id,
            "source_id": admission.source_id,
        }
        records.append(
            ExtractedSnapshot(
                source_id=admission.source_id,
                snapshot_id=snapshot_id,
                repository_numeric_id=repository_id,
                prediction_time=prediction_time,
                base_sha=base_sha,
                head_sha=head_sha,
                changed_files=changed_files,
                commit_count=commit_count,
                outcome=_outcome(record["outcome"]),
                snapshot_hash=canonical_hash(snapshot_payload),
            )
        )
    return ExtractedSource(
        admission=admission,
        payload_hash=canonical_hash(payload),
        records=tuple(sorted(records, key=lambda item: (item.prediction_time, item.snapshot_id))),
    )
