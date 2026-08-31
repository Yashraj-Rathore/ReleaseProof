from __future__ import annotations

from typing import NoReturn

import pytest
from django.db import connection

from adapters.retrieval import DeterministicEmbeddingProvider, DeterministicReranker
from apps.web.retrieval.models import (
    EMBEDDING_PHYSICAL_INDEX_V1,
    LEXICAL_PHYSICAL_INDEX_V1,
    EmbeddingIndexProfile,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbedding384,
    KnowledgeLexicalIndex,
    LexicalIndexProfile,
)
from apps.web.retrieval.services import (
    activate_embedding_profile,
    build_embedding_profile,
    ingest_evidence_document,
    retrieve_evidence,
)
from packages.retrieval_core import EvidenceDocumentInput, EvidenceSourceType, IndexLifecycle
from tests import factories

pytestmark = pytest.mark.django_db


def _scope() -> tuple[object, object]:
    organization = factories.organization(name="Retrieval Org", slug="retrieval-org")
    installation = factories.installation(
        organization=organization,
        github_installation_id=71_001,
        github_account_id=71_002,
    )
    repository = factories.repository(
        organization=organization,
        installation=installation,
        github_repository_id=71_003,
        name="retrieval-fixture",
    )
    return organization, repository


def _input(
    *,
    source_type: EvidenceSourceType,
    source_id: str,
    title: str,
    content: str,
) -> EvidenceDocumentInput:
    return EvidenceDocumentInput(
        source_type=source_type,
        source_id=source_id,
        source_version="fixture-v1",
        title=title,
        content=content,
        source_uri=f"fixture://{source_id}",
        approved=True,
    )


def _ingest_fixture(organization: object, repository: object) -> None:
    ingest_evidence_document(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        document_input=_input(
            source_type=EvidenceSourceType.RUNBOOK,
            source_id="docs/webhook-runbook.md",
            title="Webhook verification runbook",
            content=(
                "# Signature failures\n"
                "Verify the HMAC webhook signature before parsing the payload.\n\n"
                "## Rotation\nRotate the webhook secret through the approved credential reference."
            ),
        ),
    )
    ingest_evidence_document(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        document_input=_input(
            source_type=EvidenceSourceType.ADR,
            source_id="docs/adr/database-migrations.md",
            title="Database migration policy",
            content=(
                "# Forward migrations\nUse additive schema changes before application rollout.\n\n"
                "## Rollback\nPrefer forward repair over destructive reversal."
            ),
        ),
    )


def test_ingestion_is_bounded_idempotent_and_preserves_chunk_provenance() -> None:
    organization, repository = _scope()
    document_input = _input(
        source_type=EvidenceSourceType.RUNBOOK,
        source_id="docs/auth-runbook.md",
        title="Authentication runbook",
        content="# Webhooks\nVerify signatures.\n\n## Rotation\nRotate credentials safely.",
    )

    first, created = ingest_evidence_document(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        document_input=document_input,
    )
    repeated, repeated_created = ingest_evidence_document(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        document_input=document_input,
    )

    assert created is True
    assert repeated_created is False
    assert repeated.pk == first.pk
    assert first.content_sha256
    assert first.retention_policy_version == "organization-retention-policy-v1"
    assert list(first.chunks.values_list("heading", flat=True)) == ["Webhooks", "Rotation"]
    assert all(chunk.strategy.endswith("markdown-heading") for chunk in first.chunks.all())
    profile = LexicalIndexProfile.objects.get(
        repository=repository, lifecycle=IndexLifecycle.ACTIVE
    )
    assert profile.configuration == "simple"
    assert profile.entries.count() == first.chunks.count()


def test_side_by_side_embedding_build_switches_profile_without_overwriting_rows() -> None:
    organization, repository = _scope()
    _ingest_fixture(organization, repository)
    first_provider = DeterministicEmbeddingProvider(version="fixture-embedding-v1", salt="one")
    second_provider = DeterministicEmbeddingProvider(version="fixture-embedding-v2", salt="two")

    first = build_embedding_profile(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        provider=first_provider,
        activate=True,
    )
    first_row_hashes = tuple(
        first.entries.order_by("chunk_id").values_list("vector_sha256", flat=True)
    )
    second = build_embedding_profile(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        provider=second_provider,
        activate=False,
    )

    first.refresh_from_db()
    assert first.lifecycle == IndexLifecycle.ACTIVE
    assert second.lifecycle == IndexLifecycle.READY
    assert first.entries.count() == second.entries.count() == KnowledgeChunk.objects.count()
    assert (
        tuple(first.entries.order_by("chunk_id").values_list("vector_sha256", flat=True))
        == first_row_hashes
    )

    activate_embedding_profile(profile=second)
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.lifecycle == IndexLifecycle.READY
    assert second.lifecycle == IndexLifecycle.ACTIVE
    assert KnowledgeEmbedding384.objects.count() == KnowledgeChunk.objects.count() * 2
    assert (
        tuple(first.entries.order_by("chunk_id").values_list("vector_sha256", flat=True))
        == first_row_hashes
    )


def test_hybrid_retrieval_exposes_scores_filters_and_safe_reranker_fallback() -> None:
    organization, repository = _scope()
    _ingest_fixture(organization, repository)
    provider = DeterministicEmbeddingProvider()
    build_embedding_profile(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        provider=provider,
        activate=True,
    )

    response = retrieve_evidence(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        query="webhook signature verification",
        embedding_provider=provider,
        reranker_provider=DeterministicReranker(),
        source_types=(EvidenceSourceType.RUNBOOK,),
        limit=3,
    )

    assert response.lexical_status == response.semantic_status == response.reranker_status == "ok"
    assert response.query_sha256
    assert response.fusion_version == "rrf-v1-k60"
    assert response.hits
    assert all(hit.source_ref.startswith("runbook:") for hit in response.hits)
    assert response.hits[0].lexical_score is not None
    assert response.hits[0].semantic_score is not None
    assert response.hits[0].fusion_score is not None
    assert response.hits[0].reranker_score is not None

    class UnavailableReranker:
        adapter_version = "unavailable-reranker-v1"
        artifact = DeterministicReranker().artifact

        def score(self, query: str, documents: tuple[str, ...]) -> NoReturn:
            del query, documents
            raise RuntimeError("fixture provider unavailable")

    fallback = retrieve_evidence(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        query="webhook signature verification",
        embedding_provider=provider,
        reranker_provider=UnavailableReranker(),
        limit=3,
    )
    assert fallback.reranker_status == "provider_unavailable_fallback"
    assert fallback.hits
    assert all(hit.reranker_score is None for hit in fallback.hits)


def test_postgresql_physical_fts_and_dimension_compatible_vector_indexes_exist() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("physical retrieval indexes are a PostgreSQL contract")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() "
            "AND indexname IN (%s, %s)",
            [LEXICAL_PHYSICAL_INDEX_V1, EMBEDDING_PHYSICAL_INDEX_V1],
        )
        indexes = {row[0] for row in cursor.fetchall()}

    assert indexes == {LEXICAL_PHYSICAL_INDEX_V1, EMBEDDING_PHYSICAL_INDEX_V1}
    assert KnowledgeDocument.objects.count() == 0
    assert KnowledgeLexicalIndex.objects.count() == 0
    assert EmbeddingIndexProfile.objects.count() == 0
