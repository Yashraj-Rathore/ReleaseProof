"""Tenant-scoped execution and append-only persistence of safe M12 summaries."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404

from apps.web.changes.models import ChangeFeatureSet
from apps.web.evidence.models import EvidenceItem, EvidenceKind
from apps.web.organizations.models import Organization
from packages.agent_core import (
    AGENT_GRAPH_VERSION,
    AGENT_STATE_SCHEMA_VERSION,
    AgentLimits,
    AgentNodeProvider,
    BoundedInvestigationTools,
    EvidenceCategory,
    EvidenceReference,
    InvestigationRequest,
    InvestigationResult,
    ToolName,
    run_investigation,
)
from packages.recommendation_core import RecommendationInputsV1, fuse_recommendation

AGENT_EVIDENCE_SCHEMA_VERSION = "agent-investigation-evidence-v1"
AGENT_EVIDENCE_PRODUCER_VERSION = "releaseproof-agent-investigation-v1"
MAX_AGENT_INPUT_EVIDENCE = 50
DEFAULT_AGENT_LIMITS = AgentLimits()


@dataclass(frozen=True, slots=True)
class AgentEvidenceSelection:
    public_id: uuid.UUID | str
    category: EvidenceCategory


@dataclass(frozen=True, slots=True)
class PersistedAgentInvestigation:
    evidence_item: EvidenceItem
    result: InvestigationResult | None
    created: bool


def _selection_ids(
    selections: tuple[AgentEvidenceSelection, ...],
) -> tuple[uuid.UUID, ...]:
    if len(selections) > MAX_AGENT_INPUT_EVIDENCE:
        raise ValueError("agent evidence selection exceeds 50 items")
    if len({str(item.public_id) for item in selections}) != len(selections):
        raise ValueError("agent evidence selection IDs must be unique")
    try:
        return tuple(uuid.UUID(str(item.public_id)) for item in selections)
    except ValueError as error:
        raise ValueError("agent evidence selection contains an invalid identifier") from error


def _references(
    *,
    organization: Organization,
    feature_set: ChangeFeatureSet,
    selections: tuple[AgentEvidenceSelection, ...],
) -> tuple[EvidenceReference, ...]:
    public_ids = _selection_ids(selections)
    rows = list(
        EvidenceItem.objects.for_organization(organization)
        .filter(feature_set=feature_set, public_id__in=public_ids)
        .order_by("sequence", "id")
    )
    if len(rows) != len(public_ids):
        raise ValueError("agent evidence is unavailable in the active tenant/snapshot scope")
    by_id = {row.public_id: row for row in rows}
    references: list[EvidenceReference] = []
    for selection, public_id in zip(selections, public_ids, strict=True):
        row = by_id[public_id]
        status = "missing" if row.missing else "available"
        rule_hash = hashlib.sha256(row.rule_id.encode()).hexdigest()[:16]
        references.append(
            EvidenceReference(
                evidence_id=f"evidence:{row.public_id}",
                category=selection.category,
                summary=(
                    f"{selection.category.value} evidence is {status}; "
                    f"producer={row.producer_version}."
                ),
                source_reference=f"evidence:{row.public_id}",
                fact_codes=(
                    f"category:{selection.category.value}",
                    f"status:{status}",
                    f"rule_sha256_prefix:{rule_hash}",
                ),
            )
        )
    return tuple(references)


def _run_identity(
    *,
    feature_set: ChangeFeatureSet,
    selections: tuple[AgentEvidenceSelection, ...],
    policy_inputs: RecommendationInputsV1,
    provider: AgentNodeProvider,
    limits: AgentLimits,
    failed_tools: tuple[ToolName, ...],
    cancelled: bool,
) -> str:
    payload = {
        "cancelled": cancelled,
        "failed_tools": [item.value for item in failed_tools],
        "feature_set": str(feature_set.public_id),
        "graph_version": AGENT_GRAPH_VERSION,
        "limits": limits.as_dict(),
        "policy_inputs": policy_inputs.as_dict(),
        "provider": {
            "adapter_version": provider.adapter_version,
            "model_id": provider.model_id,
            "provider_name": provider.provider_name,
        },
        "selections": [
            {"category": item.category.value, "public_id": str(item.public_id)}
            for item in selections
        ],
        "state_schema_version": AGENT_STATE_SCHEMA_VERSION,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"agent:{digest}"


def _validate_provider_identity(provider: AgentNodeProvider) -> None:
    for field, value in (
        ("provider_name", provider.provider_name),
        ("model_id", provider.model_id),
        ("adapter_version", provider.adapter_version),
    ):
        if (
            not isinstance(value, str)
            or not 1 <= len(value) <= 160
            or not value.isascii()
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError(f"agent {field} is invalid")


def _persist(
    *,
    organization: Organization,
    feature_set: ChangeFeatureSet,
    rule_id: str,
    result: InvestigationResult,
    provider: AgentNodeProvider,
) -> PersistedAgentInvestigation:
    with transaction.atomic():
        locked = ChangeFeatureSet.objects.select_for_update().get(
            pk=feature_set.pk,
            organization=organization,
        )
        existing = (
            EvidenceItem.objects.for_organization(organization)
            .filter(feature_set=locked, rule_id=rule_id, kind=EvidenceKind.AGENT)
            .first()
        )
        if existing is not None:
            return PersistedAgentInvestigation(existing, None, False)
        maximum = (
            EvidenceItem.objects.for_organization(organization)
            .filter(feature_set=locked)
            .aggregate(maximum=Max("sequence"))["maximum"]
        )
        item = EvidenceItem(
            organization=organization,
            snapshot=locked.snapshot,
            feature_set=locked,
            sequence=0 if maximum is None else int(maximum) + 1,
            kind=EvidenceKind.AGENT,
            rule_id=rule_id,
            title="Bounded agent investigation",
            value={
                "provider": {
                    "adapter_version": provider.adapter_version,
                    "local_only": provider.local_only,
                    "model_id": provider.model_id,
                    "provider_name": provider.provider_name,
                },
                "result": result.safe_dict(),
                "result_sha256": result.result_sha256,
                "status": result.termination_reason.value,
            },
            reason=(
                "Bounded read-only agent trace for human review; deterministic policy remains "
                "authoritative."
            ),
            source_refs=list(result.evidence_ids or ("policy:decision",)),
            missing=result.partial,
            producer_version=AGENT_EVIDENCE_PRODUCER_VERSION,
            schema_version=AGENT_EVIDENCE_SCHEMA_VERSION,
        )
        item.full_clean()
        item.save()
        return PersistedAgentInvestigation(item, result, True)


def run_agent_investigation(
    *,
    organization: Organization,
    feature_set: ChangeFeatureSet,
    selections: tuple[AgentEvidenceSelection, ...],
    policy_inputs: RecommendationInputsV1,
    provider: AgentNodeProvider,
    limits: AgentLimits = DEFAULT_AGENT_LIMITS,
    failed_tools: tuple[ToolName, ...] = (),
    cancelled: bool = False,
) -> PersistedAgentInvestigation:
    """Run the local-only graph and persist no prompts, source blobs, or hidden reasoning."""

    if (
        feature_set.organization_id != organization.id
        or feature_set.snapshot.organization_id != organization.id
    ):
        raise ValueError("feature set is unavailable in the active organization")
    _validate_provider_identity(provider)
    if provider.local_only is not True:
        raise ValueError("M12 permits only a local provider; hosted routing is not implemented")
    run_id = _run_identity(
        feature_set=feature_set,
        selections=selections,
        policy_inputs=policy_inputs,
        provider=provider,
        limits=limits,
        failed_tools=failed_tools,
        cancelled=cancelled,
    )
    rule_id = f"agent-investigation:{run_id.removeprefix('agent:')}"
    existing = (
        EvidenceItem.objects.for_organization(organization)
        .filter(feature_set=feature_set, rule_id=rule_id, kind=EvidenceKind.AGENT)
        .first()
    )
    if existing is not None:
        return PersistedAgentInvestigation(existing, None, False)
    references = _references(
        organization=organization,
        feature_set=feature_set,
        selections=selections,
    )
    decision = fuse_recommendation(policy_inputs)
    request = InvestigationRequest(
        run_id=run_id,
        snapshot_id=str(feature_set.snapshot.public_id),
        evidence=references,
        policy_decision=decision,
        limits=limits,
        cancelled=cancelled,
    )
    result = run_investigation(
        request,
        tools=BoundedInvestigationTools(references, limits, failed_tools=failed_tools),
        provider=provider,
    )
    return _persist(
        organization=organization,
        feature_set=feature_set,
        rule_id=rule_id,
        result=result,
        provider=provider,
    )


def get_agent_investigation(
    *,
    organization: Organization,
    public_id: uuid.UUID,
) -> EvidenceItem:
    return get_object_or_404(
        EvidenceItem.objects.for_organization(organization),
        public_id=public_id,
        kind=EvidenceKind.AGENT,
    )


def serialize_agent_investigation(item: EvidenceItem) -> dict[str, object]:
    value = item.value if isinstance(item.value, dict) else {}
    return {
        "created_at": item.created_at.isoformat(),
        "evidence_id": str(item.public_id),
        "kind": item.kind,
        "missing": item.missing,
        "reason": item.reason,
        "schema_version": item.schema_version,
        "source_refs": item.source_refs,
        **value,
    }
