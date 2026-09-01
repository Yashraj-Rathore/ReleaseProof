"""Framework-light privacy routing and deterministic redaction policy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from packages.ai_core.contracts import ContentClass, EvidenceContext

POLICY_SCHEMA_VERSION = "hosted-llm-policy-v1"
ROUTER_VERSION = "privacy-router-v1"
REDACTION_VERSION = "deterministic-redaction-v1"
TERMS_REVIEW_MAX_AGE_DAYS = 365


class RoutingMode(StrEnum):
    LOCAL_ONLY = "local_only"
    HOSTED_REDACTED = "hosted_redacted"
    HOSTED_ALLOWED = "hosted_allowed"


class ProviderKind(StrEnum):
    DETERMINISTIC_FAKE = "deterministic_fake"
    LOCAL = "local"
    HOSTED = "hosted"


class TrainingUseMode(StrEnum):
    UNKNOWN = "unknown"
    NOT_USED_FOR_TRAINING = "not_used_for_training"
    CONTRACT_REVIEWED = "contract_reviewed"


class RetentionMode(StrEnum):
    UNKNOWN = "unknown"
    PROVIDER_STANDARD = "provider_standard"
    CUSTOM_DURATION = "custom_duration"
    CONTRACTUAL_ZERO_RETENTION = "contractual_zero_retention"


@dataclass(frozen=True, slots=True)
class ProviderConfiguration:
    provider_name: str
    model_id: str
    kind: ProviderKind
    region: str
    training_use_mode: TrainingUseMode
    retention_mode: RetentionMode
    retention_days: int | None
    supports_response_storage_disabled: bool

    def __post_init__(self) -> None:
        for field, value, maximum in (
            ("provider_name", self.provider_name, 128),
            ("model_id", self.model_id, 160),
            ("region", self.region, 64),
        ):
            if not value or len(value) > maximum or not value.isascii():
                raise ValueError(f"{field} is invalid")
        if self.retention_days is not None and not 0 <= self.retention_days <= 3_650:
            raise ValueError("retention_days must be null or between 0 and 3650")
        if self.retention_mode is RetentionMode.UNKNOWN and self.retention_days is not None:
            raise ValueError("unknown provider retention cannot claim a duration")


@dataclass(frozen=True, slots=True)
class PrivacyPolicySnapshot:
    policy_id: str
    policy_version: int
    policy_sha256: str
    routing_mode: RoutingMode
    allowed_providers: tuple[str, ...]
    allowed_models: tuple[str, ...]
    allowed_content_classes: tuple[ContentClass, ...]
    max_transmitted_bytes: int
    max_input_tokens: int
    max_output_tokens: int
    max_cost_microusd: int
    redaction_version: str
    training_use_mode: TrainingUseMode
    terms_reviewed_on: date | None
    retention_mode: RetentionMode
    retention_days: int | None
    allowed_regions: tuple[str, ...]
    response_storage_disabled: bool
    connect_timeout_seconds: float
    read_timeout_seconds: float
    max_attempts: int
    retry_backoff_seconds: float

    def __post_init__(self) -> None:
        if self.policy_version < 1 or len(self.policy_sha256) != 64:
            raise ValueError("policy identity is invalid")
        if not self.policy_id or not self.policy_id.isascii():
            raise ValueError("policy_id is invalid")
        if any(
            not values or len(set(values)) != len(values)
            for values in (
                self.allowed_providers,
                self.allowed_models,
                self.allowed_content_classes,
            )
        ):
            raise ValueError("policy allowlists must be non-empty and unique")
        if not 256 <= self.max_transmitted_bytes <= 131_072:
            raise ValueError("policy transmitted-byte budget is invalid")
        if not 256 <= self.max_input_tokens <= 262_144:
            raise ValueError("policy input-token budget is invalid")
        if not 64 <= self.max_output_tokens <= 8_192:
            raise ValueError("policy output-token budget is invalid")
        if not 1 <= self.max_cost_microusd <= 100_000_000:
            raise ValueError("policy cost budget is invalid")


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    allowed: bool
    reason_code: str
    router_version: str
    policy_id: str
    policy_version: int
    policy_sha256: str
    routing_mode: str
    provider_name: str
    model_id: str
    provider_kind: str
    region: str
    redaction_version: str | None
    transmitted_content_classes: tuple[str, ...]
    transmitted_bytes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "router_version": self.router_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_sha256": self.policy_sha256,
            "routing_mode": self.routing_mode,
            "provider_name": self.provider_name,
            "model_id": self.model_id,
            "provider_kind": self.provider_kind,
            "region": self.region,
            "redaction_version": self.redaction_version,
            "transmitted_content_classes": list(self.transmitted_content_classes),
            "transmitted_bytes": self.transmitted_bytes,
        }


@dataclass(frozen=True, slots=True)
class RoutingResult:
    decision: RoutingDecision
    evidence: tuple[EvidenceContext, ...]


_REDACTIONS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)\b(?:authorization|api[_-]?key|token|secret|password)\s*[:=]\s*\S+"),
    re.compile(r"\b(?:gh[pousr]_|sk-)[A-Za-z0-9_-]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+PRIVATE KEY-----"),
)


def redact_text(value: str, *, version: str) -> str:
    if version != REDACTION_VERSION:
        raise ValueError("redaction version is unsupported")
    redacted = value
    for pattern in _REDACTIONS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _decision(
    *,
    policy: PrivacyPolicySnapshot,
    provider: ProviderConfiguration,
    allowed: bool,
    reason_code: str,
    evidence: tuple[EvidenceContext, ...] = (),
    redaction_version: str | None = None,
) -> RoutingResult:
    content_classes = tuple(sorted({item.content_class.value for item in evidence}))
    byte_count = sum(len(item.content.encode()) for item in evidence)
    return RoutingResult(
        decision=RoutingDecision(
            allowed=allowed,
            reason_code=reason_code,
            router_version=ROUTER_VERSION,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            policy_sha256=policy.policy_sha256,
            routing_mode=policy.routing_mode.value,
            provider_name=provider.provider_name,
            model_id=provider.model_id,
            provider_kind=provider.kind.value,
            region=provider.region,
            redaction_version=redaction_version,
            transmitted_content_classes=content_classes,
            transmitted_bytes=byte_count,
        ),
        evidence=evidence if allowed else (),
    )


def route_evidence(
    *,
    policy: PrivacyPolicySnapshot,
    provider: ProviderConfiguration,
    evidence: tuple[EvidenceContext, ...],
    today: date,
) -> RoutingResult:
    """Return allowed data or a content-free fail-closed decision."""

    if provider.provider_name not in policy.allowed_providers:
        return _decision(
            policy=policy, provider=provider, allowed=False, reason_code="provider_not_allowed"
        )
    if provider.model_id not in policy.allowed_models:
        return _decision(
            policy=policy, provider=provider, allowed=False, reason_code="model_not_allowed"
        )
    if any(item.content_class not in policy.allowed_content_classes for item in evidence):
        return _decision(
            policy=policy, provider=provider, allowed=False, reason_code="content_class_not_allowed"
        )
    if policy.routing_mode is RoutingMode.LOCAL_ONLY and provider.kind is ProviderKind.HOSTED:
        return _decision(
            policy=policy, provider=provider, allowed=False, reason_code="hosted_route_disabled"
        )
    if (
        policy.routing_mode is not RoutingMode.LOCAL_ONLY
        and provider.kind is not ProviderKind.HOSTED
    ):
        return _decision(
            policy=policy, provider=provider, allowed=False, reason_code="hosted_provider_required"
        )

    routed = evidence
    redaction_version: str | None = None
    if policy.routing_mode is RoutingMode.HOSTED_REDACTED:
        if policy.redaction_version != REDACTION_VERSION:
            return _decision(
                policy=policy,
                provider=provider,
                allowed=False,
                reason_code="redaction_version_incompatible",
            )
        routed = tuple(
            EvidenceContext(
                evidence_id=item.evidence_id,
                content_class=item.content_class,
                content=redact_text(item.content, version=policy.redaction_version),
                source_reference=redact_text(
                    item.source_reference, version=policy.redaction_version
                ),
            )
            for item in evidence
        )
        redaction_version = policy.redaction_version

    if provider.kind is ProviderKind.HOSTED:
        oldest_allowed = today - timedelta(days=TERMS_REVIEW_MAX_AGE_DAYS)
        if (
            policy.terms_reviewed_on is None
            or not oldest_allowed <= policy.terms_reviewed_on <= today
            or policy.training_use_mode is TrainingUseMode.UNKNOWN
            or provider.training_use_mode is TrainingUseMode.UNKNOWN
            or provider.training_use_mode is not policy.training_use_mode
        ):
            return _decision(
                policy=policy,
                provider=provider,
                allowed=False,
                reason_code="training_terms_incompatible",
            )
        if (
            policy.retention_mode is RetentionMode.UNKNOWN
            or provider.retention_mode is RetentionMode.UNKNOWN
            or provider.retention_mode is not policy.retention_mode
            or provider.retention_days != policy.retention_days
        ):
            return _decision(
                policy=policy,
                provider=provider,
                allowed=False,
                reason_code="retention_incompatible",
            )
        if provider.region not in policy.allowed_regions:
            return _decision(
                policy=policy, provider=provider, allowed=False, reason_code="region_not_allowed"
            )
        if policy.response_storage_disabled and not provider.supports_response_storage_disabled:
            return _decision(
                policy=policy,
                provider=provider,
                allowed=False,
                reason_code="response_storage_control_unavailable",
            )

    transmitted_bytes = sum(len(item.content.encode()) for item in routed)
    if transmitted_bytes > policy.max_transmitted_bytes:
        return _decision(
            policy=policy,
            provider=provider,
            allowed=False,
            reason_code="transmission_size_exceeded",
        )
    return _decision(
        policy=policy,
        provider=provider,
        allowed=True,
        reason_code="route_allowed",
        evidence=routed,
        redaction_version=redaction_version,
    )
