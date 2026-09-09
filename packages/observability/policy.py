"""Versioned independent abuse-control and retention contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

OPERATIONAL_POLICY_SCHEMA_VERSION = "operational-policy-v1"


class QuotaScope(StrEnum):
    TENANT = "tenant"
    USER = "user"


class QuotaKind(StrEnum):
    WEBHOOK_REQUESTS_PER_MINUTE = "webhook_requests_per_minute"
    ANALYSIS_REQUESTS_PER_HOUR = "analysis_requests_per_hour"
    RETRIEVAL_QUERIES_PER_MINUTE = "retrieval_queries_per_minute"
    EMBEDDING_ITEMS_PER_DAY = "embedding_items_per_day"
    LLM_REQUESTS_PER_HOUR = "llm_requests_per_hour"
    LLM_TOKENS_PER_DAY = "llm_tokens_per_day"
    LLM_COST_MICROUSD_PER_DAY = "llm_cost_microusd_per_day"
    RUNNER_JOBS_PER_HOUR = "runner_jobs_per_hour"
    RUNNER_CPU_SECONDS_PER_DAY = "runner_cpu_seconds_per_day"
    UPLOAD_BYTES_PER_REQUEST = "upload_bytes_per_request"
    UPLOAD_REQUESTS_PER_HOUR = "upload_requests_per_hour"


class RetentionClass(StrEnum):
    SOURCE_SNAPSHOT = "source_snapshot"
    EMBEDDING = "embedding"
    ARTIFACT = "artifact"
    ANALYSIS = "analysis"


DEFAULT_QUOTA_LIMITS: Mapping[str, int] = MappingProxyType(
    {
        QuotaKind.WEBHOOK_REQUESTS_PER_MINUTE.value: 120,
        QuotaKind.ANALYSIS_REQUESTS_PER_HOUR.value: 100,
        QuotaKind.RETRIEVAL_QUERIES_PER_MINUTE.value: 120,
        QuotaKind.EMBEDDING_ITEMS_PER_DAY.value: 10_000,
        QuotaKind.LLM_REQUESTS_PER_HOUR.value: 100,
        QuotaKind.LLM_TOKENS_PER_DAY.value: 1_000_000,
        QuotaKind.LLM_COST_MICROUSD_PER_DAY.value: 10_000_000,
        QuotaKind.RUNNER_JOBS_PER_HOUR.value: 20,
        QuotaKind.RUNNER_CPU_SECONDS_PER_DAY.value: 3_600,
        QuotaKind.UPLOAD_BYTES_PER_REQUEST.value: 1_048_576,
        QuotaKind.UPLOAD_REQUESTS_PER_HOUR.value: 20,
    }
)

DEFAULT_RETENTION_DAYS: Mapping[str, int] = MappingProxyType(
    {
        RetentionClass.SOURCE_SNAPSHOT.value: 365,
        RetentionClass.EMBEDDING.value: 365,
        RetentionClass.ARTIFACT.value: 365,
        RetentionClass.ANALYSIS.value: 365,
    }
)

_MAX_LIMIT = 1_000_000_000


def _validate_exact_integer_map(
    value: object,
    *,
    expected: frozenset[str],
    field: str,
    minimum: int,
) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{field} must contain exactly the supported versioned keys")
    normalized: dict[str, int] = {}
    for key, item in value.items():
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"{field}.{key} must be an integer")
        if not minimum <= item <= _MAX_LIMIT:
            raise ValueError(f"{field}.{key} is outside the supported bound")
        normalized[key] = item
    return normalized


def validate_quota_limits(value: object) -> dict[str, int]:
    return _validate_exact_integer_map(
        value,
        expected=frozenset(item.value for item in QuotaKind),
        field="quota_limits",
        minimum=1,
    )


def validate_retention_days(value: object) -> dict[str, int]:
    return _validate_exact_integer_map(
        value,
        expected=frozenset(item.value for item in RetentionClass),
        field="retention_days",
        minimum=1,
    )


def canonical_policy_hash(
    *,
    schema_version: str,
    version: int,
    quota_limits: Mapping[str, int],
    retention_days: Mapping[str, int],
) -> str:
    payload = {
        "quota_limits": dict(sorted(quota_limits.items())),
        "retention_days": dict(sorted(retention_days.items())),
        "schema_version": schema_version,
        "version": version,
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(canonical).hexdigest()
