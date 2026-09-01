from __future__ import annotations

import json

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction

from adapters.llm import FAKE_PROVIDER_CONFIGURATION, FakeLLMProvider
from apps.web.analysis.change_intelligence import analyze_snapshot_for_organization
from apps.web.analysis.llm_evidence import analyze_llm_evidence
from apps.web.evidence.models import EvidenceItem, EvidenceKind
from apps.web.organizations.models import HostedLLMPolicy, MembershipRole
from apps.web.retrieval.services import ingest_evidence_document
from packages.ai_core import (
    REDACTION_VERSION,
    ContentClass,
    LLMUnavailableError,
    RetentionMode,
    RoutingMode,
    TrainingUseMode,
)
from packages.retrieval_core import EvidenceDocumentInput, EvidenceSourceType
from tests import factories
from tests.integration.test_change_intelligence_persistence import _snapshot

pytestmark = pytest.mark.django_db


def _scope(*, suffix: str, number: int) -> tuple[object, object, object]:
    organization = factories.organization(name=f"LLM {suffix}", slug=f"llm-{suffix}")
    installation = factories.installation(
        organization=organization,
        github_installation_id=90_000 + number,
        github_account_id=91_000 + number,
    )
    repository = factories.repository(
        organization=organization,
        installation=installation,
        github_repository_id=92_000 + number,
        name=f"llm-{suffix}",
    )
    snapshot = _snapshot(
        tenant=organization,
        github_installation=installation,
        bound_repository=repository,
        label=str(number),
        path="src/auth/policy.py",
        author_key=None,
        failed=None,
    )
    feature_set, _created = analyze_snapshot_for_organization(
        organization=organization,
        snapshot_public_id=snapshot.public_id,
    )
    return organization, repository, feature_set


def _local_policy(organization: object, repository: object | None, *, version: int = 1) -> object:
    policy = HostedLLMPolicy(
        organization=organization,
        repository=repository,
        version=version,
        routing_mode=RoutingMode.LOCAL_ONLY,
        allowed_providers=[FAKE_PROVIDER_CONFIGURATION.provider_name],
        allowed_models=[FAKE_PROVIDER_CONFIGURATION.model_id],
        allowed_content_classes=[
            ContentClass.DETERMINISTIC_EVIDENCE,
            ContentClass.RETRIEVAL_EXCERPT,
        ],
        max_transmitted_bytes=32_768,
        max_input_tokens=49_152,
        max_output_tokens=1_024,
        max_cost_microusd=100_000,
        redaction_version=REDACTION_VERSION,
        training_use_mode=TrainingUseMode.UNKNOWN,
        retention_mode=RetentionMode.UNKNOWN,
        allowed_regions=["local"],
        response_storage_disabled=True,
        approved_by_role=MembershipRole.ADMIN,
    )
    policy.full_clean()
    policy.save()
    return policy


def test_local_fake_persists_only_safe_structured_cited_advisory_output() -> None:
    organization, repository, feature_set = _scope(suffix="persist", number=31)
    _local_policy(organization, repository)
    source_sentinel = "repository-source-sentinel-must-not-be-persisted-in-llm-output"
    document, _created = ingest_evidence_document(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        document_input=EvidenceDocumentInput(
            source_type=EvidenceSourceType.RUNBOOK,
            source_id="runbooks/auth.md",
            source_version="v1",
            title="Auth runbook",
            content=f"# Verification\nVerify signatures. {source_sentinel}",
            source_uri="fixture://runbooks/auth.md",
            approved=True,
        ),
    )
    deterministic = (
        EvidenceItem.objects.filter(feature_set=feature_set).order_by("sequence").first()
    )
    assert deterministic is not None
    chunk = document.chunks.first()
    assert chunk is not None
    provider = FakeLLMProvider()

    first = analyze_llm_evidence(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        feature_set=feature_set,  # type: ignore[arg-type]
        provider=provider,
        provider_configuration=provider.configuration,
        evidence_item_ids=(deterministic.public_id,),
        knowledge_chunk_ids=(chunk.public_id,),
    )
    repeated = analyze_llm_evidence(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        feature_set=feature_set,  # type: ignore[arg-type]
        provider=provider,
        provider_configuration=provider.configuration,
        evidence_item_ids=(deterministic.public_id,),
        knowledge_chunk_ids=(chunk.public_id,),
    )

    assert first.created is True
    assert repeated.created is False
    assert repeated.evidence_item.pk == first.evidence_item.pk
    assert provider.call_count == 1
    assert first.evidence_item.kind == EvidenceKind.LLM
    assert first.evidence_item.value["status"] == "completed"
    assert first.evidence_item.value["advisory_only"] is True
    assert first.evidence_item.value["suggestion"]["summary_evidence_ids"]
    persisted = json.dumps(first.evidence_item.value, sort_keys=True)
    assert source_sentinel not in persisted
    assert "input_text" not in persisted
    assert "chain" not in persisted.lower()


def test_missing_policy_and_provider_failure_preserve_existing_evidence_without_secrets() -> None:
    organization, repository, feature_set = _scope(suffix="failure", number=32)
    deterministic_count = EvidenceItem.objects.filter(feature_set=feature_set).count()
    provider = FakeLLMProvider()

    denied = analyze_llm_evidence(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        feature_set=feature_set,  # type: ignore[arg-type]
        provider=provider,
        provider_configuration=provider.configuration,
    )
    assert denied.status == "policy_denied"
    assert denied.evidence_item.missing is True
    assert provider.call_count == 0
    assert EvidenceItem.objects.filter(feature_set=feature_set).count() == deterministic_count + 1

    _local_policy(organization, repository)
    failure_marker = "provider-error-sensitive-marker-must-not-persist"
    unavailable = FakeLLMProvider(failure=LLMUnavailableError(failure_marker))
    failed = analyze_llm_evidence(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        feature_set=feature_set,  # type: ignore[arg-type]
        provider=unavailable,
        provider_configuration=unavailable.configuration,
    )
    assert failed.status == "llm_provider_unavailable"
    assert failed.evidence_item.missing is True
    assert failure_marker not in json.dumps(failed.evidence_item.value)
    assert EvidenceItem.objects.filter(
        feature_set=feature_set, kind=EvidenceKind.DETERMINISTIC
    ).exists()


def test_repository_policy_override_wins_and_cross_tenant_selection_fails_closed() -> None:
    organization_a, repository_a, feature_set_a = _scope(suffix="tenant-a", number=33)
    organization_b, repository_b, feature_set_b = _scope(suffix="tenant-b", number=34)
    _local_policy(organization_a, None, version=1)
    _local_policy(organization_a, repository_a, version=2)
    document_b, _created = ingest_evidence_document(
        organization=organization_b,  # type: ignore[arg-type]
        repository=repository_b,  # type: ignore[arg-type]
        document_input=EvidenceDocumentInput(
            source_type=EvidenceSourceType.RUNBOOK,
            source_id="runbooks/private-b.md",
            source_version="v1",
            title="Private tenant B",
            content="# Tenant B\nprivate-tenant-b-marker",
            source_uri="fixture://runbooks/private-b.md",
            approved=True,
        ),
    )
    chunk_b = document_b.chunks.first()
    assert chunk_b is not None

    with pytest.raises(ValueError, match="active tenant/repository"):
        analyze_llm_evidence(
            organization=organization_a,  # type: ignore[arg-type]
            repository=repository_a,  # type: ignore[arg-type]
            feature_set=feature_set_a,  # type: ignore[arg-type]
            provider=FakeLLMProvider(),
            provider_configuration=FAKE_PROVIDER_CONFIGURATION,
            knowledge_chunk_ids=(chunk_b.public_id,),
        )
    with pytest.raises(ValueError, match="feature set"):
        analyze_llm_evidence(
            organization=organization_a,  # type: ignore[arg-type]
            repository=repository_a,  # type: ignore[arg-type]
            feature_set=feature_set_b,  # type: ignore[arg-type]
            provider=FakeLLMProvider(),
            provider_configuration=FAKE_PROVIDER_CONFIGURATION,
        )


def test_database_rejects_cross_tenant_and_raw_policy_mutation() -> None:
    organization_a, _repository_a, _feature_set_a = _scope(suffix="policy-a", number=35)
    _organization_b, repository_b, _feature_set_b = _scope(suffix="policy-b", number=36)
    with pytest.raises(IntegrityError), transaction.atomic():
        HostedLLMPolicy.objects.create(
            organization=organization_a,
            repository=repository_b,
            version=1,
            routing_mode=RoutingMode.LOCAL_ONLY,
            allowed_providers=[FAKE_PROVIDER_CONFIGURATION.provider_name],
            allowed_models=[FAKE_PROVIDER_CONFIGURATION.model_id],
            allowed_content_classes=[ContentClass.DETERMINISTIC_EVIDENCE],
            training_use_mode=TrainingUseMode.UNKNOWN,
            retention_mode=RetentionMode.UNKNOWN,
            allowed_regions=["local"],
            approved_by_role=MembershipRole.ADMIN,
        )

    policy = _local_policy(organization_a, None, version=2)
    table = connection.ops.quote_name(HostedLLMPolicy._meta.db_table)
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table} SET version = %s WHERE id = %s",  # noqa: S608
            [99, policy.id],  # type: ignore[attr-defined]
        )
