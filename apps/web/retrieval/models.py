"""Tenant-bound historical evidence and side-by-side lexical/vector indexes."""

from __future__ import annotations

import hashlib
import uuid
from typing import NoReturn

from django.contrib.postgres.search import SearchVectorField
from django.core.exceptions import ValidationError
from django.db import models
from pgvector.django import VectorField

from apps.web.changes.models import ImmutableQuerySet, validate_checksum
from apps.web.organizations.models import Organization
from apps.web.repositories.models import Repository
from packages.retrieval_core import FTS_CONFIGURATION, EvidenceSourceType, IndexLifecycle

EMBEDDING_DIMENSION_V1 = 384
EMBEDDING_PHYSICAL_TABLE_V1 = "retrieval_knowledgeembedding384"
EMBEDDING_PHYSICAL_INDEX_V1 = "retrieval_embedding384_cosine_hnsw_v1"
LEXICAL_PHYSICAL_INDEX_V1 = "retrieval_lexical_search_gin_v1"


def _organization_id(value: Organization | int) -> int:
    return value.pk if isinstance(value, Organization) else value


class ScopedImmutableQuerySet[Model: models.Model](ImmutableQuerySet[Model]):
    def for_scope(
        self,
        *,
        organization: Organization | int,
        repository: Repository | int,
    ) -> ScopedImmutableQuerySet[Model]:
        repository_id = repository.pk if isinstance(repository, Repository) else repository
        return self.filter(
            organization_id=_organization_id(organization),
            repository_id=repository_id,
        )


class ScopedProfileQuerySet[Model: models.Model](models.QuerySet[Model]):
    def for_scope(
        self,
        *,
        organization: Organization | int,
        repository: Repository | int,
    ) -> ScopedProfileQuerySet[Model]:
        repository_id = repository.pk if isinstance(repository, Repository) else repository
        return self.filter(
            organization_id=_organization_id(organization),
            repository_id=repository_id,
        )


class KnowledgeDocument(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="knowledge_documents",
    )
    repository = models.ForeignKey(
        Repository,
        on_delete=models.PROTECT,
        related_name="knowledge_documents",
    )
    source_type = models.CharField(
        max_length=32,
        choices=[(item.value, item.value) for item in EvidenceSourceType],
    )
    source_id = models.CharField(max_length=512)
    source_version = models.CharField(max_length=128)
    source_uri = models.CharField(max_length=1_200)
    title = models.CharField(max_length=256)
    content_text = models.TextField()
    content_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    content_byte_count = models.PositiveIntegerField()
    chunking_version = models.CharField(max_length=64)
    retention_class = models.CharField(max_length=32)
    retention_policy_version = models.CharField(max_length=64)
    retain_until = models.DateTimeField()
    approved_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ScopedImmutableQuerySet["KnowledgeDocument"].as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "repository", "id"),
                name="retrieval_document_org_repo_id_unique",
            ),
            models.UniqueConstraint(
                fields=(
                    "repository",
                    "source_type",
                    "source_id",
                    "source_version",
                    "content_sha256",
                    "chunking_version",
                ),
                name="retrieval_document_identity_unique",
            ),
        ]
        ordering = ("organization_id", "repository_id", "source_type", "source_id")

    def clean(self) -> None:
        super().clean()
        if (
            self.repository_id
            and self.organization_id
            and self.repository.organization_id != self.organization_id
        ):
            raise ValidationError("knowledge document and repository organizations must match")
        content_bytes = self.content_text.encode("utf-8")
        if self.content_byte_count != len(content_bytes):
            raise ValidationError("document byte count does not match content")
        if hashlib.sha256(content_bytes).hexdigest() != self.content_sha256:
            raise ValidationError("document checksum does not match content")
        if self.retain_until <= self.approved_at:
            raise ValidationError("document retention must end after approval")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("knowledge documents are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError(
            "knowledge documents are immutable before governed retention deletion"
        )


class KnowledgeChunk(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="knowledge_chunks",
    )
    repository = models.ForeignKey(
        Repository,
        on_delete=models.PROTECT,
        related_name="knowledge_chunks",
    )
    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.PROTECT,
        related_name="chunks",
    )
    sequence = models.PositiveSmallIntegerField()
    heading = models.CharField(max_length=256)
    content_text = models.TextField()
    normalized_text = models.TextField()
    content_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    start_line = models.PositiveIntegerField()
    end_line = models.PositiveIntegerField()
    chunking_version = models.CharField(max_length=64)
    normalizer_version = models.CharField(max_length=64)
    strategy = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ScopedImmutableQuerySet["KnowledgeChunk"].as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "repository", "id"),
                name="retrieval_chunk_org_repo_id_unique",
            ),
            models.UniqueConstraint(
                fields=("document", "chunking_version", "sequence"),
                name="retrieval_chunk_document_version_sequence_unique",
            ),
        ]
        ordering = ("document_id", "sequence")

    def clean(self) -> None:
        super().clean()
        if (
            self.organization_id
            and self.repository_id
            and self.repository.organization_id != self.organization_id
        ):
            raise ValidationError("knowledge chunk and repository organizations must match")
        if self.organization_id and self.document_id:
            if self.document.organization_id != self.organization_id:
                raise ValidationError("knowledge chunk and document organizations must match")
            if self.document.repository_id != self.repository_id:
                raise ValidationError("knowledge chunk and document repositories must match")
        if self.end_line < self.start_line:
            raise ValidationError("chunk line range is invalid")
        if hashlib.sha256(self.content_text.encode("utf-8")).hexdigest() != self.content_sha256:
            raise ValidationError("chunk checksum does not match content")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("knowledge chunks are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("knowledge chunks are immutable before governed retention deletion")


class LexicalIndexProfile(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="lexical_index_profiles",
    )
    repository = models.ForeignKey(
        Repository,
        on_delete=models.PROTECT,
        related_name="lexical_index_profiles",
    )
    version = models.CharField(max_length=64)
    configuration = models.CharField(max_length=32, default=FTS_CONFIGURATION)
    normalizer_version = models.CharField(max_length=64)
    chunking_version = models.CharField(max_length=64)
    physical_index_name = models.CharField(max_length=96, default=LEXICAL_PHYSICAL_INDEX_V1)
    lifecycle = models.CharField(
        max_length=16,
        choices=[(item.value, item.value) for item in IndexLifecycle],
        default=IndexLifecycle.BUILDING,
    )
    build_error_code = models.CharField(max_length=64, blank=True)
    built_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ScopedProfileQuerySet["LexicalIndexProfile"].as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "repository", "id"),
                name="retrieval_lexical_profile_org_repo_id_unique",
            ),
            models.UniqueConstraint(
                fields=("repository", "version"),
                name="retrieval_lexical_profile_repo_version_unique",
            ),
            models.UniqueConstraint(
                fields=("organization", "repository"),
                condition=models.Q(lifecycle=IndexLifecycle.ACTIVE),
                name="retrieval_one_active_lexical_profile",
            ),
        ]
        ordering = ("organization_id", "repository_id", "version")

    def clean(self) -> None:
        super().clean()
        if (
            self.repository_id
            and self.organization_id
            and self.repository.organization_id != self.organization_id
        ):
            raise ValidationError("lexical profile and repository organizations must match")
        if self.configuration != FTS_CONFIGURATION:
            raise ValidationError("M6 lexical profiles require PostgreSQL simple configuration")
        if self.physical_index_name != LEXICAL_PHYSICAL_INDEX_V1:
            raise ValidationError("lexical profile names an unsupported physical index")


class KnowledgeLexicalIndex(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="knowledge_lexical_indexes",
    )
    repository = models.ForeignKey(
        Repository,
        on_delete=models.PROTECT,
        related_name="knowledge_lexical_indexes",
    )
    chunk = models.ForeignKey(
        KnowledgeChunk,
        on_delete=models.PROTECT,
        related_name="lexical_indexes",
    )
    profile = models.ForeignKey(
        LexicalIndexProfile,
        on_delete=models.PROTECT,
        related_name="entries",
    )
    search_document = models.TextField()
    search_vector = SearchVectorField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ScopedImmutableQuerySet["KnowledgeLexicalIndex"].as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("profile", "chunk"),
                name="retrieval_lexical_profile_chunk_unique",
            )
        ]
        ordering = ("profile_id", "chunk_id")

    def clean(self) -> None:
        super().clean()
        if (
            self.organization_id
            and self.repository_id
            and self.repository.organization_id != self.organization_id
        ):
            raise ValidationError("lexical index and repository organizations must match")
        if (
            self.organization_id
            and self.chunk_id
            and (
                self.chunk.organization_id != self.organization_id
                or self.chunk.repository_id != self.repository_id
            )
        ):
            raise ValidationError("lexical index and chunk scope must match")
        if (
            self.organization_id
            and self.profile_id
            and (
                self.profile.organization_id != self.organization_id
                or self.profile.repository_id != self.repository_id
            )
        ):
            raise ValidationError("lexical index and profile scope must match")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("lexical index entries are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("lexical index entries are immutable")


class EmbeddingIndexProfile(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="embedding_index_profiles",
    )
    repository = models.ForeignKey(
        Repository,
        on_delete=models.PROTECT,
        related_name="embedding_index_profiles",
    )
    version = models.CharField(max_length=96)
    model_id = models.CharField(max_length=256)
    model_revision = models.CharField(max_length=40)
    artifact_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    artifact_license = models.CharField(max_length=64)
    dimension = models.PositiveSmallIntegerField(default=EMBEDDING_DIMENSION_V1)
    adapter_version = models.CharField(max_length=64)
    chunking_version = models.CharField(max_length=64)
    physical_table_name = models.CharField(max_length=96, default=EMBEDDING_PHYSICAL_TABLE_V1)
    physical_index_name = models.CharField(max_length=96, default=EMBEDDING_PHYSICAL_INDEX_V1)
    lifecycle = models.CharField(
        max_length=16,
        choices=[(item.value, item.value) for item in IndexLifecycle],
        default=IndexLifecycle.BUILDING,
    )
    build_error_code = models.CharField(max_length=64, blank=True)
    built_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ScopedProfileQuerySet["EmbeddingIndexProfile"].as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "repository", "id"),
                name="retrieval_embedding_profile_org_repo_id_unique",
            ),
            models.UniqueConstraint(
                fields=("repository", "version"),
                name="retrieval_embedding_profile_repo_version_unique",
            ),
            models.UniqueConstraint(
                fields=("organization", "repository"),
                condition=models.Q(lifecycle=IndexLifecycle.ACTIVE),
                name="retrieval_one_active_embedding_profile",
            ),
            models.CheckConstraint(
                condition=models.Q(dimension=EMBEDDING_DIMENSION_V1),
                name="retrieval_embedding_profile_dimension_v1",
            ),
        ]
        ordering = ("organization_id", "repository_id", "version")

    def clean(self) -> None:
        super().clean()
        if (
            self.repository_id
            and self.organization_id
            and self.repository.organization_id != self.organization_id
        ):
            raise ValidationError("embedding profile and repository organizations must match")
        if self.dimension != EMBEDDING_DIMENSION_V1:
            raise ValidationError(
                "an incompatible dimension requires a new physical embedding table"
            )
        if self.physical_table_name != EMBEDDING_PHYSICAL_TABLE_V1:
            raise ValidationError("embedding profile names an incompatible physical table")
        if self.physical_index_name != EMBEDDING_PHYSICAL_INDEX_V1:
            raise ValidationError("embedding profile names an incompatible physical index")


class KnowledgeEmbedding384(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="knowledge_embeddings_384",
    )
    repository = models.ForeignKey(
        Repository,
        on_delete=models.PROTECT,
        related_name="knowledge_embeddings_384",
    )
    chunk = models.ForeignKey(
        KnowledgeChunk,
        on_delete=models.PROTECT,
        related_name="embeddings_384",
    )
    profile = models.ForeignKey(
        EmbeddingIndexProfile,
        on_delete=models.PROTECT,
        related_name="entries",
    )
    vector = VectorField(dimensions=EMBEDDING_DIMENSION_V1)
    vector_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ScopedImmutableQuerySet["KnowledgeEmbedding384"].as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("profile", "chunk"),
                name="retrieval_embedding_profile_chunk_unique",
            )
        ]
        ordering = ("profile_id", "chunk_id")

    def clean(self) -> None:
        super().clean()
        if (
            self.organization_id
            and self.repository_id
            and self.repository.organization_id != self.organization_id
        ):
            raise ValidationError("embedding and repository organizations must match")
        if (
            self.organization_id
            and self.chunk_id
            and (
                self.chunk.organization_id != self.organization_id
                or self.chunk.repository_id != self.repository_id
            )
        ):
            raise ValidationError("embedding and chunk scope must match")
        if self.organization_id and self.profile_id:
            if (
                self.profile.organization_id != self.organization_id
                or self.profile.repository_id != self.repository_id
            ):
                raise ValidationError("embedding and profile scope must match")
            if self.profile.dimension != EMBEDDING_DIMENSION_V1:
                raise ValidationError("embedding profile dimension is incompatible")
        try:
            dimension = len(self.vector)
        except TypeError as error:
            raise ValidationError("embedding vector is not a bounded numeric sequence") from error
        if dimension != EMBEDDING_DIMENSION_V1:
            raise ValidationError("embedding vector dimension is incompatible")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("knowledge embeddings are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("knowledge embeddings are immutable")
