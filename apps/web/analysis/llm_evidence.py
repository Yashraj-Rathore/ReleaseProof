"""Tenant-scoped M7 routing, provider invocation, and safe evidence persistence."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.web.changes.models import ChangeFeatureSet
from apps.web.evidence.models import EvidenceItem, EvidenceKind
from apps.web.organizations.models import Organization
from apps.web.organizations.services import llm_policy_snapshot, resolve_effective_llm_policy
from apps.web.repositories.models import Repository
from apps.web.retrieval.models import KnowledgeChunk
from packages.ai_core import (
    ANALYSIS_SCHEMA_VERSION,
    PROMPT_IDENTITY,
    AnalysisLLMProvider,
    ContentClass,
    EvidenceContext,
    LLMAnalysisRequest,
    LLMBudget,
    LLMProviderError,
    LLMSchemaError,
    ProviderConfiguration,
    ProviderKind,
    build_analysis_request,
    route_evidence,
    validate_suggestion_citations,
)

LLM_ANALYSIS_PRODUCER_VERSION = "releaseproof-llm-analysis-v1"
MAX_SELECTED_EVIDENCE = 50
PROMPT_OVERHEAD_BYTES = 16_384


@dataclass(frozen=True, slots=True)
class LLMAnalysisResult:
    evidence_item: EvidenceItem
    created: bool
    status: str


def _uuid_tuple(values: tuple[uuid.UUID | str, ...], *, field: str) -> tuple[uuid.UUID, ...]:
    if len(values) > MAX_SELECTED_EVIDENCE or len(set(map(str, values))) != len(values):
        raise ValueError(f"{field} must contain at most 50 unique identifiers")
    try:
        return tuple(uuid.UUID(str(value)) for value in values)
    except ValueError as error:
        raise ValueError(f"{field} contains an invalid identifier") from error


def _load_context(
    *,
    organization: Organization,
    repository: Repository,
    feature_set: ChangeFeatureSet,
    evidence_item_ids: tuple[uuid.UUID | str, ...],
    knowledge_chunk_ids: tuple[uuid.UUID | str, ...],
) -> tuple[EvidenceContext, ...]:
    evidence_ids = _uuid_tuple(evidence_item_ids, field="evidence_item_ids")
    chunk_ids = _uuid_tuple(knowledge_chunk_ids, field="knowledge_chunk_ids")
    if len(evidence_ids) + len(chunk_ids) > MAX_SELECTED_EVIDENCE:
        raise ValueError("combined evidence selection exceeds 50 items")
    evidence_rows = list(
        EvidenceItem.objects.for_organization(organization)
        .filter(feature_set=feature_set, public_id__in=evidence_ids)
        .order_by("sequence", "id")
    )
    chunks = list(
        KnowledgeChunk.objects.for_scope(
            organization=organization,
            repository=repository,
        )
        .filter(public_id__in=chunk_ids, document__retain_until__gt=timezone.now())
        .select_related("document")
        .order_by("document_id", "sequence", "id")
    )
    if len(evidence_rows) != len(evidence_ids) or len(chunks) != len(chunk_ids):
        raise ValueError("selected evidence is unavailable in the active tenant/repository scope")
    contexts = [
        EvidenceContext(
            evidence_id=f"evidence:{row.public_id}",
            content_class=ContentClass.DETERMINISTIC_EVIDENCE,
            content=json.dumps(
                {
                    "missing": row.missing,
                    "reason": row.reason,
                    "title": row.title,
                    "value": row.value,
                },
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
            source_reference=f"evidence:{row.public_id}",
        )
        for row in evidence_rows
    ]
    contexts.extend(
        EvidenceContext(
            evidence_id=f"chunk:{row.public_id}",
            content_class=ContentClass.RETRIEVAL_EXCERPT,
            content=row.content_text,
            source_reference=(
                f"{row.document.source_type}:{row.document.source_id}:"
                f"{row.document.source_version}:chunk:{row.public_id}"
            ),
        )
        for row in chunks
    )
    return tuple(contexts)


def _request_rule_id(
    *,
    feature_set: ChangeFeatureSet,
    provider: ProviderConfiguration,
    policy_reference: str,
    evidence_ids: tuple[str, ...],
) -> str:
    payload = {
        "feature_set": str(feature_set.public_id),
        "provider": provider.provider_name,
        "model": provider.model_id,
        "policy": policy_reference,
        "prompt": PROMPT_IDENTITY.prompt_sha256,
        "schema": PROMPT_IDENTITY.schema_sha256,
        "evidence_ids": list(evidence_ids),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"llm-analysis:{digest}"


def _persist_result(
    *,
    organization: Organization,
    feature_set: ChangeFeatureSet,
    rule_id: str,
    status: str,
    reason: str,
    value: dict[str, object],
    source_refs: tuple[str, ...],
    missing: bool,
) -> LLMAnalysisResult:
    with transaction.atomic():
        locked_feature = ChangeFeatureSet.objects.select_for_update().get(
            pk=feature_set.pk,
            organization=organization,
        )
        existing = (
            EvidenceItem.objects.for_organization(organization)
            .filter(feature_set=locked_feature, rule_id=rule_id)
            .first()
        )
        if existing is not None:
            existing_status = (
                str(existing.value.get("status", "unknown"))
                if isinstance(existing.value, dict)
                else "unknown"
            )
            return LLMAnalysisResult(existing, False, existing_status)
        maximum = (
            EvidenceItem.objects.for_organization(organization)
            .filter(feature_set=locked_feature)
            .aggregate(maximum=Max("sequence"))["maximum"]
        )
        item = EvidenceItem(
            organization=organization,
            snapshot=locked_feature.snapshot,
            feature_set=locked_feature,
            sequence=0 if maximum is None else int(maximum) + 1,
            kind=EvidenceKind.LLM,
            rule_id=rule_id,
            title="Evidence-grounded LLM advisory analysis",
            value=value,
            reason=reason,
            source_refs=list(source_refs or ("policy:decision",)),
            missing=missing,
            producer_version=LLM_ANALYSIS_PRODUCER_VERSION,
            schema_version=ANALYSIS_SCHEMA_VERSION,
        )
        item.full_clean()
        item.save()
        return LLMAnalysisResult(item, True, status)


def _failure_value(
    *,
    status: str,
    provider: ProviderConfiguration,
    decision: dict[str, object],
) -> dict[str, object]:
    return {
        "status": status,
        "advisory_only": True,
        "provider": {
            "provider_name": provider.provider_name,
            "model_id": provider.model_id,
            "provider_kind": provider.kind.value,
        },
        "routing_decision": decision,
        "prompt": {
            "prompt_version": PROMPT_IDENTITY.prompt_version,
            "prompt_sha256": PROMPT_IDENTITY.prompt_sha256,
            "schema_version": PROMPT_IDENTITY.schema_version,
            "schema_sha256": PROMPT_IDENTITY.schema_sha256,
        },
        "suggestion": None,
    }


def analyze_llm_evidence(
    *,
    organization: Organization,
    repository: Repository,
    feature_set: ChangeFeatureSet,
    provider: AnalysisLLMProvider,
    provider_configuration: ProviderConfiguration,
    evidence_item_ids: tuple[uuid.UUID | str, ...] = (),
    knowledge_chunk_ids: tuple[uuid.UUID | str, ...] = (),
    cancelled: bool = False,
) -> LLMAnalysisResult:
    """Run one policy-gated advisory analysis and persist no raw provider context."""

    if repository.organization_id != organization.id:
        raise ValueError("repository is unavailable in the active organization")
    if (
        feature_set.organization_id != organization.id
        or feature_set.snapshot.repository_id != repository.id
    ):
        raise ValueError("feature set is unavailable in the active tenant/repository scope")
    contexts = _load_context(
        organization=organization,
        repository=repository,
        feature_set=feature_set,
        evidence_item_ids=evidence_item_ids,
        knowledge_chunk_ids=knowledge_chunk_ids,
    )
    policy = resolve_effective_llm_policy(
        organization=organization,
        repository=repository,
    )
    policy_reference = str(policy.public_id) if policy is not None else "missing"
    rule_id = _request_rule_id(
        feature_set=feature_set,
        provider=provider_configuration,
        policy_reference=policy_reference,
        evidence_ids=tuple(item.evidence_id for item in contexts),
    )
    existing = (
        EvidenceItem.objects.for_organization(organization)
        .filter(feature_set=feature_set, rule_id=rule_id)
        .first()
    )
    if existing is not None:
        status = (
            str(existing.value.get("status", "unknown"))
            if isinstance(existing.value, dict)
            else "unknown"
        )
        return LLMAnalysisResult(existing, False, status)

    if policy is None:
        decision = {
            "allowed": False,
            "reason_code": "policy_missing",
            "provider_name": provider_configuration.provider_name,
            "model_id": provider_configuration.model_id,
            "transmitted_bytes": 0,
            "transmitted_content_classes": [],
        }
        return _persist_result(
            organization=organization,
            feature_set=feature_set,
            rule_id=rule_id,
            status="policy_denied",
            reason="LLM analysis not run because an effective privacy policy is missing.",
            value=_failure_value(
                status="policy_denied",
                provider=provider_configuration,
                decision=decision,
            ),
            source_refs=(),
            missing=True,
        )

    policy_snapshot = llm_policy_snapshot(policy)
    if provider_configuration.kind is ProviderKind.HOSTED and not organization.hosted_llm_enabled:
        decision = {
            "allowed": False,
            "reason_code": "hosted_llm_disabled",
            "policy_id": policy_snapshot.policy_id,
            "policy_version": policy_snapshot.policy_version,
            "policy_sha256": policy_snapshot.policy_sha256,
            "provider_name": provider_configuration.provider_name,
            "model_id": provider_configuration.model_id,
            "transmitted_bytes": 0,
            "transmitted_content_classes": [],
        }
        return _persist_result(
            organization=organization,
            feature_set=feature_set,
            rule_id=rule_id,
            status="policy_denied",
            reason="LLM analysis not run because hosted LLM use is disabled.",
            value=_failure_value(
                status="policy_denied",
                provider=provider_configuration,
                decision=decision,
            ),
            source_refs=(),
            missing=True,
        )
    routed = route_evidence(
        policy=policy_snapshot,
        provider=provider_configuration,
        evidence=contexts,
        today=timezone.localdate(),
    )
    decision = routed.decision.as_dict()
    if not routed.decision.allowed:
        return _persist_result(
            organization=organization,
            feature_set=feature_set,
            rule_id=rule_id,
            status="policy_denied",
            reason=f"LLM analysis not run: {routed.decision.reason_code}.",
            value=_failure_value(
                status="policy_denied",
                provider=provider_configuration,
                decision=decision,
            ),
            source_refs=(),
            missing=True,
        )

    budget = LLMBudget(
        max_input_bytes=min(
            262_144,
            policy_snapshot.max_transmitted_bytes + PROMPT_OVERHEAD_BYTES,
        ),
        max_input_tokens=policy_snapshot.max_input_tokens,
        max_output_tokens=policy_snapshot.max_output_tokens,
        max_cost_microusd=policy_snapshot.max_cost_microusd,
        connect_timeout_seconds=policy_snapshot.connect_timeout_seconds,
        read_timeout_seconds=policy_snapshot.read_timeout_seconds,
        max_attempts=policy_snapshot.max_attempts,
        retry_backoff_seconds=policy_snapshot.retry_backoff_seconds,
    )
    try:
        request: LLMAnalysisRequest = build_analysis_request(
            change_id=f"snapshot:{feature_set.snapshot.public_id}",
            evidence=routed.evidence,
            budget=budget,
            cancelled=cancelled,
        )
        response = provider.analyze_change(request)
        if (
            response.provider_name != provider_configuration.provider_name
            or response.model_id != provider_configuration.model_id
        ):
            raise LLMSchemaError("provider response identity differs from the routed provider")
        validate_suggestion_citations(
            response.suggestion,
            allowed_evidence_ids=request.allowed_evidence_ids,
        )
    except LLMProviderError as error:
        status = error.error_code
        return _persist_result(
            organization=organization,
            feature_set=feature_set,
            rule_id=rule_id,
            status=status,
            reason=f"LLM advisory evidence is unavailable: {status}.",
            value=_failure_value(
                status=status,
                provider=provider_configuration,
                decision=decision,
            ),
            source_refs=tuple(item.evidence_id for item in routed.evidence),
            missing=True,
        )

    return _persist_result(
        organization=organization,
        feature_set=feature_set,
        rule_id=rule_id,
        status="completed",
        reason="Advisory synthesis from cited allowed evidence; deterministic policy is unchanged.",
        value={
            "status": "completed",
            "advisory_only": True,
            "provider": {
                "provider_name": response.provider_name,
                "model_id": response.model_id,
                "adapter_version": response.adapter_version,
                "sdk_version": response.sdk_version,
            },
            "routing_decision": decision,
            "prompt": {
                "prompt_version": request.prompt.prompt_version,
                "prompt_sha256": request.prompt.prompt_sha256,
                "schema_version": request.prompt.schema_version,
                "schema_sha256": request.prompt.schema_sha256,
            },
            "usage": response.usage.as_dict(),
            "elapsed_ms": round(response.elapsed_ms, 6),
            "suggestion": response.suggestion.as_dict(),
        },
        source_refs=tuple(item.evidence_id for item in routed.evidence),
        missing=response.suggestion.insufficient_evidence,
    )
