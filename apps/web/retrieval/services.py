"""Tenant-scoped evidence ingestion, indexing, activation, and hybrid retrieval."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import IntegrityError, connection, transaction
from django.db.models import Value
from django.utils import timezone
from pgvector.django import CosineDistance

from apps.web.organizations.models import Organization
from apps.web.repositories.models import Repository, RepositoryLifecycle
from apps.web.retrieval.models import (
    EMBEDDING_DIMENSION_V1,
    EMBEDDING_PHYSICAL_INDEX_V1,
    EMBEDDING_PHYSICAL_TABLE_V1,
    LEXICAL_PHYSICAL_INDEX_V1,
    EmbeddingIndexProfile,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbedding384,
    KnowledgeLexicalIndex,
    LexicalIndexProfile,
)
from packages.retrieval_core import (
    CHUNKING_VERSION,
    FTS_CONFIGURATION,
    FTS_PROFILE_VERSION,
    FUSION_VERSION,
    NORMALIZER_VERSION,
    RERANKER_VERSION,
    RETRIEVAL_SCHEMA_VERSION,
    ChunkCandidate,
    EmbeddingProvider,
    EvidenceDocumentInput,
    EvidenceSourceType,
    IndexLifecycle,
    RerankerProvider,
    RetrievalHit,
    chunk_document,
    cosine_similarity,
    lexical_score,
    normalize_fts_text,
    normalize_source_text,
    reciprocal_rank_fusion,
    rerank_candidates,
)
from packages.retrieval_core.contracts import MAX_CANDIDATES, MAX_RETURNED_HITS, validate_query

MAX_INDEX_CHUNKS = 5_000
EMBEDDING_BATCH_SIZE = 32


@dataclass(frozen=True, slots=True)
class RetrievalResponse:
    schema_version: str
    query_sha256: str
    lexical_profile_version: str | None
    embedding_profile_version: str | None
    fusion_version: str
    reranker_version: str | None
    lexical_status: str
    semantic_status: str
    reranker_status: str
    hits: tuple[RetrievalHit, ...]


def _validate_scope(*, organization: Organization, repository: Repository) -> None:
    if repository.organization_id != organization.id:
        raise ValueError("repository is unavailable in the active organization")
    if repository.lifecycle != RepositoryLifecycle.ACTIVE or not repository.indexing_enabled:
        raise ValueError("repository evidence indexing is disabled")


def _retention_version(organization: Organization) -> str:
    return f"organization-retention-policy-v{organization.policy_version}"


def _source_ref(chunk: KnowledgeChunk) -> str:
    document = chunk.document
    return (
        f"{document.source_type}:{document.source_id}@{document.source_version}"
        f"#chunk={chunk.public_id}"
    )


def ingest_evidence_document(
    *,
    organization: Organization,
    repository: Repository,
    document_input: EvidenceDocumentInput,
) -> tuple[KnowledgeDocument, bool]:
    """Persist one approved inert document and source-aware chunks idempotently."""

    _validate_scope(organization=organization, repository=repository)
    normalized_content = normalize_source_text(document_input.content)
    content_bytes = normalized_content.encode("utf-8")
    content_sha256 = hashlib.sha256(content_bytes).hexdigest()
    chunks = chunk_document(document_input)
    now = timezone.now()
    identity = {
        "repository": repository,
        "source_type": document_input.source_type.value,
        "source_id": document_input.source_id,
        "source_version": document_input.source_version,
        "content_sha256": content_sha256,
        "chunking_version": CHUNKING_VERSION,
    }
    existing = (
        KnowledgeDocument.objects.for_scope(
            organization=organization,
            repository=repository,
        )
        .filter(**identity)
        .first()
    )
    if existing is not None:
        _index_chunks_for_active_lexical_profile(
            organization=organization,
            repository=repository,
        )
        return existing, False
    try:
        with transaction.atomic():
            record = KnowledgeDocument(
                organization=organization,
                source_uri=document_input.source_uri,
                title=document_input.title,
                content_text=normalized_content,
                content_byte_count=len(content_bytes),
                retention_class=document_input.retention_class,
                retention_policy_version=_retention_version(organization),
                retain_until=now + timedelta(days=organization.metadata_retention_days),
                approved_at=now,
                **identity,
            )
            record.full_clean()
            record.save()
            for chunk in chunks:
                chunk_record = KnowledgeChunk(
                    organization=organization,
                    repository=repository,
                    document=record,
                    sequence=chunk.sequence,
                    heading=chunk.heading,
                    content_text=chunk.content,
                    normalized_text=chunk.normalized_text,
                    content_sha256=chunk.content_sha256,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    chunking_version=CHUNKING_VERSION,
                    normalizer_version=NORMALIZER_VERSION,
                    strategy=chunk.strategy,
                )
                chunk_record.full_clean()
                chunk_record.save()
    except IntegrityError:
        existing = KnowledgeDocument.objects.for_scope(
            organization=organization,
            repository=repository,
        ).get(**identity)
        return existing, False
    ensure_default_lexical_profile(
        organization=organization,
        repository=repository,
        activate=True,
    )
    return record, True


def _create_lexical_entry(*, profile: LexicalIndexProfile, chunk: KnowledgeChunk) -> None:
    search_document = normalize_fts_text(
        f"{chunk.document.title}\n{chunk.heading}\n{chunk.normalized_text}"
    )
    search_vector: Any = None
    if connection.vendor == "postgresql":
        search_vector = SearchVector(Value(search_document), config=FTS_CONFIGURATION)
    entry = KnowledgeLexicalIndex(
        organization=profile.organization,
        repository=profile.repository,
        profile=profile,
        chunk=chunk,
        search_document=search_document,
        search_vector=search_vector,
    )
    entry.full_clean(exclude={"search_vector"})
    entry.save()


def _index_missing_lexical_chunks(*, profile: LexicalIndexProfile) -> None:
    chunks = KnowledgeChunk.objects.for_scope(
        organization=profile.organization,
        repository=profile.repository,
    ).filter(
        chunking_version=profile.chunking_version,
        normalizer_version=profile.normalizer_version,
        document__retain_until__gt=timezone.now(),
    )
    if chunks.count() > MAX_INDEX_CHUNKS:
        raise ValueError("repository chunk count exceeds the M6 lexical index bound")
    existing_ids = set(profile.entries.values_list("chunk_id", flat=True))
    for chunk in chunks.select_related("document").order_by("id"):
        if chunk.id not in existing_ids:
            _create_lexical_entry(profile=profile, chunk=chunk)


def activate_lexical_profile(*, profile: LexicalIndexProfile) -> LexicalIndexProfile:
    with transaction.atomic():
        locked = LexicalIndexProfile.objects.select_for_update().get(pk=profile.pk)
        if locked.lifecycle not in {IndexLifecycle.READY, IndexLifecycle.ACTIVE}:
            raise ValueError("only a ready lexical profile can be activated")
        LexicalIndexProfile.objects.for_scope(
            organization=locked.organization,
            repository=locked.repository,
        ).filter(lifecycle=IndexLifecycle.ACTIVE).exclude(pk=locked.pk).update(
            lifecycle=IndexLifecycle.READY,
            activated_at=None,
        )
        locked.lifecycle = IndexLifecycle.ACTIVE
        locked.activated_at = timezone.now()
        locked.full_clean()
        locked.save(update_fields=("lifecycle", "activated_at"))
        return locked


def ensure_default_lexical_profile(
    *,
    organization: Organization,
    repository: Repository,
    activate: bool,
) -> LexicalIndexProfile:
    _validate_scope(organization=organization, repository=repository)
    profile, _created = LexicalIndexProfile.objects.get_or_create(
        organization=organization,
        repository=repository,
        version=FTS_PROFILE_VERSION,
        defaults={
            "configuration": FTS_CONFIGURATION,
            "normalizer_version": NORMALIZER_VERSION,
            "chunking_version": CHUNKING_VERSION,
            "physical_index_name": LEXICAL_PHYSICAL_INDEX_V1,
            "lifecycle": IndexLifecycle.BUILDING,
        },
    )
    try:
        with transaction.atomic():
            _index_missing_lexical_chunks(profile=profile)
            profile.lifecycle = (
                IndexLifecycle.ACTIVE
                if profile.lifecycle == IndexLifecycle.ACTIVE
                else IndexLifecycle.READY
            )
            profile.build_error_code = ""
            profile.built_at = timezone.now()
            profile.full_clean()
            profile.save(update_fields=("lifecycle", "build_error_code", "built_at"))
    except (IntegrityError, RuntimeError, ValueError):
        LexicalIndexProfile.objects.filter(pk=profile.pk).update(
            lifecycle=IndexLifecycle.FAILED,
            build_error_code="lexical_build_failed",
        )
        raise
    if activate:
        return activate_lexical_profile(profile=profile)
    return profile


def _index_chunks_for_active_lexical_profile(
    *,
    organization: Organization,
    repository: Repository,
) -> None:
    profile = (
        LexicalIndexProfile.objects.for_scope(
            organization=organization,
            repository=repository,
        )
        .filter(lifecycle=IndexLifecycle.ACTIVE)
        .first()
    )
    if profile is not None:
        _index_missing_lexical_chunks(profile=profile)


def _vector_hash(vector: tuple[float, ...]) -> str:
    payload = json.dumps(vector, allow_nan=False, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _validate_embedding_vector(vector: tuple[float, ...], *, dimension: int) -> None:
    if len(vector) != dimension or any(not math.isfinite(value) for value in vector):
        raise ValueError("embedding provider returned an invalid vector")


def activate_embedding_profile(*, profile: EmbeddingIndexProfile) -> EmbeddingIndexProfile:
    with transaction.atomic():
        locked = EmbeddingIndexProfile.objects.select_for_update().get(pk=profile.pk)
        if locked.lifecycle not in {IndexLifecycle.READY, IndexLifecycle.ACTIVE}:
            raise ValueError("only a ready embedding profile can be activated")
        expected = (
            KnowledgeChunk.objects.for_scope(
                organization=locked.organization,
                repository=locked.repository,
            )
            .filter(
                chunking_version=locked.chunking_version,
                document__retain_until__gt=timezone.now(),
            )
            .count()
        )
        if locked.entries.count() != expected:
            raise ValueError("embedding profile is incomplete and cannot be activated")
        EmbeddingIndexProfile.objects.for_scope(
            organization=locked.organization,
            repository=locked.repository,
        ).filter(lifecycle=IndexLifecycle.ACTIVE).exclude(pk=locked.pk).update(
            lifecycle=IndexLifecycle.READY,
            activated_at=None,
        )
        locked.lifecycle = IndexLifecycle.ACTIVE
        locked.activated_at = timezone.now()
        locked.full_clean()
        locked.save(update_fields=("lifecycle", "activated_at"))
        return locked


def build_embedding_profile(
    *,
    organization: Organization,
    repository: Repository,
    provider: EmbeddingProvider,
    activate: bool,
) -> EmbeddingIndexProfile:
    _validate_scope(organization=organization, repository=repository)
    artifact = provider.artifact
    if artifact.dimension != EMBEDDING_DIMENSION_V1:
        raise ValueError("embedding artifact requires an unsupported physical dimension")
    profile, created = EmbeddingIndexProfile.objects.get_or_create(
        organization=organization,
        repository=repository,
        version=artifact.version,
        defaults={
            "model_id": artifact.model_id,
            "model_revision": artifact.revision,
            "artifact_sha256": artifact.safetensors_sha256,
            "artifact_license": artifact.license,
            "dimension": artifact.dimension,
            "adapter_version": provider.adapter_version,
            "chunking_version": CHUNKING_VERSION,
            "physical_table_name": EMBEDDING_PHYSICAL_TABLE_V1,
            "physical_index_name": EMBEDDING_PHYSICAL_INDEX_V1,
            "lifecycle": IndexLifecycle.BUILDING,
        },
    )
    expected_identity = (
        artifact.model_id,
        artifact.revision,
        artifact.safetensors_sha256,
        artifact.dimension,
        provider.adapter_version,
    )
    actual_identity = (
        profile.model_id,
        profile.model_revision,
        profile.artifact_sha256,
        profile.dimension,
        profile.adapter_version,
    )
    if not created and actual_identity != expected_identity:
        raise ValueError("embedding profile version is already bound to another artifact")
    chunks = list(
        KnowledgeChunk.objects.for_scope(
            organization=organization,
            repository=repository,
        )
        .filter(chunking_version=CHUNKING_VERSION, document__retain_until__gt=timezone.now())
        .select_related("document")
        .order_by("id")[: MAX_INDEX_CHUNKS + 1]
    )
    if len(chunks) > MAX_INDEX_CHUNKS:
        raise ValueError("repository chunk count exceeds the M6 embedding index bound")
    existing_ids = set(profile.entries.values_list("chunk_id", flat=True))
    missing = [chunk for chunk in chunks if chunk.id not in existing_ids]
    try:
        for start in range(0, len(missing), EMBEDDING_BATCH_SIZE):
            batch = missing[start : start + EMBEDDING_BATCH_SIZE]
            vectors = provider.embed(tuple(chunk.content_text for chunk in batch))
            if len(vectors) != len(batch):
                raise ValueError("embedding provider returned the wrong vector count")
            with transaction.atomic():
                for chunk, vector in zip(batch, vectors, strict=True):
                    _validate_embedding_vector(vector, dimension=profile.dimension)
                    entry = KnowledgeEmbedding384(
                        organization=organization,
                        repository=repository,
                        chunk=chunk,
                        profile=profile,
                        vector=list(vector),
                        vector_sha256=_vector_hash(vector),
                    )
                    entry.full_clean()
                    entry.save()
        profile.lifecycle = IndexLifecycle.READY
        profile.build_error_code = ""
        profile.built_at = timezone.now()
        profile.full_clean()
        profile.save(update_fields=("lifecycle", "build_error_code", "built_at"))
    except (IntegrityError, OSError, RuntimeError, TypeError, ValueError):
        EmbeddingIndexProfile.objects.filter(pk=profile.pk).update(
            lifecycle=IndexLifecycle.FAILED,
            build_error_code="embedding_build_failed",
        )
        raise
    if activate:
        return activate_embedding_profile(profile=profile)
    return profile


def _lexical_candidates(
    *,
    organization: Organization,
    repository: Repository,
    query: str,
    source_types: tuple[EvidenceSourceType, ...],
    limit: int,
) -> tuple[tuple[ChunkCandidate, ...], str | None, str]:
    profile = (
        LexicalIndexProfile.objects.for_scope(
            organization=organization,
            repository=repository,
        )
        .filter(lifecycle=IndexLifecycle.ACTIVE)
        .first()
    )
    if profile is None:
        return (), None, "unavailable"
    queryset = KnowledgeLexicalIndex.objects.for_scope(
        organization=organization,
        repository=repository,
    ).filter(profile=profile, chunk__document__retain_until__gt=timezone.now())
    if source_types:
        queryset = queryset.filter(
            chunk__document__source_type__in=[item.value for item in source_types]
        )
    if connection.vendor == "postgresql":
        search_query = SearchQuery(
            normalize_fts_text(query), config=FTS_CONFIGURATION, search_type="plain"
        )
        rows = (
            queryset.annotate(
                component_rank=SearchRank("search_vector", search_query, normalization=32)
            )
            .filter(component_rank__gt=0)
            .select_related("chunk__document")
            .order_by("-component_rank", "chunk__public_id")[:limit]
        )
        candidates = tuple(
            ChunkCandidate(
                chunk_id=str(row.chunk.public_id),
                content=row.chunk.content_text,
                source_ref=_source_ref(row.chunk),
                lexical_score=float(row.component_rank),
            )
            for row in rows
        )
    else:
        scored = [
            (
                lexical_score(query, row.search_document),
                row,
            )
            for row in queryset.select_related("chunk__document")
        ]
        scored.sort(key=lambda pair: (-pair[0], str(pair[1].chunk.public_id)))
        candidates = tuple(
            ChunkCandidate(
                chunk_id=str(row.chunk.public_id),
                content=row.chunk.content_text,
                source_ref=_source_ref(row.chunk),
                lexical_score=score,
            )
            for score, row in scored[:limit]
            if score > 0.0
        )
    return candidates, profile.version, "ok"


def _as_vector_tuple(value: object) -> tuple[float, ...]:
    if hasattr(value, "to_list"):
        value = value.to_list()
    elif hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        raise ValueError("stored embedding vector is invalid")
    return tuple(float(item) for item in value)


def _semantic_candidates(
    *,
    organization: Organization,
    repository: Repository,
    query: str,
    source_types: tuple[EvidenceSourceType, ...],
    provider: EmbeddingProvider | None,
    limit: int,
) -> tuple[tuple[ChunkCandidate, ...], str | None, str]:
    profile = (
        EmbeddingIndexProfile.objects.for_scope(
            organization=organization,
            repository=repository,
        )
        .filter(lifecycle=IndexLifecycle.ACTIVE)
        .first()
    )
    if profile is None or provider is None:
        return (), profile.version if profile else None, "unavailable"
    artifact = provider.artifact
    identity = (
        artifact.version,
        artifact.model_id,
        artifact.revision,
        artifact.safetensors_sha256,
        artifact.dimension,
        provider.adapter_version,
    )
    if identity != (
        profile.version,
        profile.model_id,
        profile.model_revision,
        profile.artifact_sha256,
        profile.dimension,
        profile.adapter_version,
    ):
        return (), profile.version, "model_mismatch"
    try:
        vectors = provider.embed((query,))
        if len(vectors) != 1:
            raise ValueError("embedding provider returned the wrong query-vector count")
        query_vector = vectors[0]
        _validate_embedding_vector(query_vector, dimension=profile.dimension)
    except (OSError, RuntimeError, TypeError, ValueError):
        return (), profile.version, "provider_unavailable"
    queryset = KnowledgeEmbedding384.objects.for_scope(
        organization=organization,
        repository=repository,
    ).filter(profile=profile, chunk__document__retain_until__gt=timezone.now())
    if source_types:
        queryset = queryset.filter(
            chunk__document__source_type__in=[item.value for item in source_types]
        )
    if connection.vendor == "postgresql":
        rows = (
            queryset.annotate(component_distance=CosineDistance("vector", list(query_vector)))
            .select_related("chunk__document")
            .order_by("component_distance", "chunk__public_id")[:limit]
        )
        candidates = tuple(
            ChunkCandidate(
                chunk_id=str(row.chunk.public_id),
                content=row.chunk.content_text,
                source_ref=_source_ref(row.chunk),
                semantic_score=1.0 - float(row.component_distance),
            )
            for row in rows
        )
    else:
        scored = [
            (cosine_similarity(query_vector, _as_vector_tuple(row.vector)), row)
            for row in queryset.select_related("chunk__document")
        ]
        scored.sort(key=lambda pair: (-pair[0], str(pair[1].chunk.public_id)))
        candidates = tuple(
            ChunkCandidate(
                chunk_id=str(row.chunk.public_id),
                content=row.chunk.content_text,
                source_ref=_source_ref(row.chunk),
                semantic_score=score,
            )
            for score, row in scored[:limit]
        )
    return candidates, profile.version, "ok"


def retrieve_evidence(
    *,
    organization: Organization,
    repository: Repository,
    query: str,
    embedding_provider: EmbeddingProvider | None,
    reranker_provider: RerankerProvider | None = None,
    source_types: tuple[EvidenceSourceType, ...] = (),
    limit: int = 10,
) -> RetrievalResponse:
    _validate_scope(organization=organization, repository=repository)
    bounded_query = validate_query(query)
    if not 1 <= limit <= MAX_RETURNED_HITS:
        raise ValueError("retrieval result limit is outside the bounded contract")
    pool_limit = min(MAX_CANDIDATES, max(limit * 3, limit))
    lexical, lexical_version, lexical_status = _lexical_candidates(
        organization=organization,
        repository=repository,
        query=bounded_query,
        source_types=source_types,
        limit=pool_limit,
    )
    semantic, embedding_version, semantic_status = _semantic_candidates(
        organization=organization,
        repository=repository,
        query=bounded_query,
        source_types=source_types,
        provider=embedding_provider,
        limit=pool_limit,
    )
    fused = reciprocal_rank_fusion(lexical, semantic, limit=pool_limit)
    reranker_status = "disabled"
    reranker_version: str | None = None
    ranked = fused
    if reranker_provider is not None and fused:
        reranker_version = reranker_provider.artifact.version
        try:
            ranked = rerank_candidates(
                query=bounded_query,
                candidates=fused,
                provider=reranker_provider,
                limit=pool_limit,
            )
            reranker_status = "ok"
        except (OSError, RuntimeError, TypeError, ValueError):
            ranked = fused
            reranker_status = "provider_unavailable_fallback"
    hits = tuple(
        RetrievalHit(
            chunk_id=item.chunk_id,
            source_ref=item.source_ref,
            content=item.content,
            rank=rank,
            lexical_score=item.lexical_score,
            semantic_score=item.semantic_score,
            lexical_rank=item.lexical_rank,
            semantic_rank=item.semantic_rank,
            fusion_score=item.fusion_score,
            reranker_score=item.reranker_score,
        )
        for rank, item in enumerate(ranked[:limit], start=1)
    )
    return RetrievalResponse(
        schema_version=RETRIEVAL_SCHEMA_VERSION,
        query_sha256=hashlib.sha256(bounded_query.encode()).hexdigest(),
        lexical_profile_version=lexical_version,
        embedding_profile_version=embedding_version,
        fusion_version=FUSION_VERSION,
        reranker_version=reranker_version
        if reranker_version != RERANKER_VERSION
        else RERANKER_VERSION,
        lexical_status=lexical_status,
        semantic_status=semantic_status,
        reranker_status=reranker_status,
        hits=hits,
    )
