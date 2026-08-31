from __future__ import annotations

import hashlib
from datetime import timedelta

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone

from adapters.retrieval import DeterministicEmbeddingProvider
from apps.web.retrieval.models import KnowledgeDocument
from apps.web.retrieval.services import ingest_evidence_document, retrieve_evidence
from packages.retrieval_core import CHUNKING_VERSION, EvidenceDocumentInput, EvidenceSourceType
from tests import factories

pytestmark = pytest.mark.django_db


def _tenant(*, suffix: str, number: int) -> tuple[object, object]:
    organization = factories.organization(name=f"Tenant {suffix}", slug=f"tenant-{suffix}")
    installation = factories.installation(
        organization=organization,
        github_installation_id=80_000 + number,
        github_account_id=81_000 + number,
    )
    repository = factories.repository(
        organization=organization,
        installation=installation,
        github_repository_id=82_000 + number,
        name=f"repository-{suffix}",
    )
    return organization, repository


def _document(source_id: str, marker: str) -> EvidenceDocumentInput:
    return EvidenceDocumentInput(
        source_type=EvidenceSourceType.RUNBOOK,
        source_id=source_id,
        source_version="v1",
        title="Tenant runbook",
        content=f"# Authentication\nVerify webhook signatures. {marker}",
        source_uri=f"fixture://{source_id}",
        approved=True,
    )


def test_retrieval_queries_cannot_cross_tenant_or_repository_scope() -> None:
    organization_a, repository_a = _tenant(suffix="a", number=1)
    organization_b, repository_b = _tenant(suffix="b", number=2)
    ingest_evidence_document(
        organization=organization_a,  # type: ignore[arg-type]
        repository=repository_a,  # type: ignore[arg-type]
        document_input=_document("runbooks/a.md", "tenant-a-marker"),
    )
    ingest_evidence_document(
        organization=organization_b,  # type: ignore[arg-type]
        repository=repository_b,  # type: ignore[arg-type]
        document_input=_document("runbooks/b.md", "tenant-b-marker"),
    )

    response = retrieve_evidence(
        organization=organization_a,  # type: ignore[arg-type]
        repository=repository_a,  # type: ignore[arg-type]
        query="webhook signatures tenant marker",
        embedding_provider=None,
    )

    assert response.hits
    assert all("runbooks/a.md" in hit.source_ref for hit in response.hits)
    assert all("tenant-b-marker" not in hit.content for hit in response.hits)
    with pytest.raises(ValueError, match="active organization"):
        retrieve_evidence(
            organization=organization_a,  # type: ignore[arg-type]
            repository=repository_b,  # type: ignore[arg-type]
            query="webhook signatures",
            embedding_provider=DeterministicEmbeddingProvider(),
        )
    with pytest.raises(ValueError, match="active organization"):
        ingest_evidence_document(
            organization=organization_a,  # type: ignore[arg-type]
            repository=repository_b,  # type: ignore[arg-type]
            document_input=_document("runbooks/cross.md", "forbidden"),
        )


def test_database_rejects_cross_tenant_document_and_raw_mutation() -> None:
    organization_a, _repository_a = _tenant(suffix="constraint-a", number=11)
    _organization_b, repository_b = _tenant(suffix="constraint-b", number=12)
    content = "# Cross tenant\nThis row must never persist."
    now = timezone.now()
    with pytest.raises(IntegrityError), transaction.atomic():
        KnowledgeDocument.objects.create(
            organization=organization_a,
            repository=repository_b,
            source_type=EvidenceSourceType.RUNBOOK,
            source_id="runbooks/cross.md",
            source_version="v1",
            source_uri="fixture://runbooks/cross.md",
            title="Cross tenant",
            content_text=content,
            content_sha256=hashlib.sha256(content.encode()).hexdigest(),
            content_byte_count=len(content.encode()),
            chunking_version=CHUNKING_VERSION,
            retention_class="source_index",
            retention_policy_version="organization-retention-policy-v1",
            retain_until=now + timedelta(days=30),
            approved_at=now,
        )

    organization, repository = _tenant(suffix="immutable", number=13)
    document, _created = ingest_evidence_document(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        document_input=_document("runbooks/immutable.md", "immutable"),
    )
    quoted_table = connection.ops.quote_name(KnowledgeDocument._meta.db_table)
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {quoted_table} SET title = %s WHERE id = %s",  # noqa: S608
            ["mutated", document.id],
        )
