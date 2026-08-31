"""Strict framework-neutral schemas for evidence ingestion and retrieval providers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from packages.retrieval_core.config import ModelArtifact

MAX_DOCUMENT_BYTES = 262_144
MAX_TITLE_CHARS = 256
MAX_SOURCE_ID_CHARS = 512
MAX_SOURCE_VERSION_CHARS = 128
MAX_SOURCE_URI_CHARS = 1_200
MAX_QUERY_CHARS = 512
MAX_QUERY_BYTES = 2_048
MAX_CANDIDATES = 50
MAX_RETURNED_HITS = 20


class EvidenceSourceType(StrEnum):
    PR_SUMMARY = "pr_summary"
    ADR = "adr"
    INCIDENT = "incident"
    POSTMORTEM = "postmortem"
    RUNBOOK = "runbook"
    DOCUMENTATION = "documentation"
    PYTHON_SOURCE = "python_source"


class IndexLifecycle(StrEnum):
    BUILDING = "building"
    READY = "ready"
    ACTIVE = "active"
    RETIRED = "retired"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class EvidenceDocumentInput:
    source_type: EvidenceSourceType
    source_id: str
    source_version: str
    title: str
    content: str
    source_uri: str
    approved: bool
    retention_class: str = "source_index"

    def __post_init__(self) -> None:
        if not self.approved:
            raise ValueError("evidence content must be explicitly approved before ingestion")
        if not 1 <= len(self.source_id) <= MAX_SOURCE_ID_CHARS or "\x00" in self.source_id:
            raise ValueError("source ID is outside the bounded contract")
        if not 1 <= len(self.source_version) <= MAX_SOURCE_VERSION_CHARS:
            raise ValueError("source version is outside the bounded contract")
        if not 1 <= len(self.title) <= MAX_TITLE_CHARS or "\x00" in self.title:
            raise ValueError("document title is outside the bounded contract")
        if not 1 <= len(self.source_uri) <= MAX_SOURCE_URI_CHARS or "\x00" in self.source_uri:
            raise ValueError("source URI is outside the bounded contract")
        if not self.content or len(self.content.encode("utf-8")) > MAX_DOCUMENT_BYTES:
            raise ValueError("document content is empty or exceeds the ingestion byte limit")
        if self.retention_class not in {"source_index", "metadata", "incident_record"}:
            raise ValueError("retention class is not approved for evidence ingestion")


@dataclass(frozen=True, slots=True)
class SourceChunk:
    sequence: int
    heading: str
    content: str
    normalized_text: str
    start_line: int
    end_line: int
    strategy: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class ChunkCandidate:
    chunk_id: str
    content: str
    source_ref: str
    lexical_score: float | None = None
    semantic_score: float | None = None
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    fusion_score: float | None = None
    reranker_score: float | None = None


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    chunk_id: str
    source_ref: str
    content: str
    rank: int
    lexical_score: float | None
    semantic_score: float | None
    lexical_rank: int | None
    semantic_rank: int | None
    fusion_score: float | None
    reranker_score: float | None


class EmbeddingProvider(Protocol):
    @property
    def artifact(self) -> ModelArtifact: ...

    @property
    def adapter_version(self) -> str: ...

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class RerankerProvider(Protocol):
    @property
    def artifact(self) -> ModelArtifact: ...

    @property
    def adapter_version(self) -> str: ...

    def score(self, query: str, documents: tuple[str, ...]) -> tuple[float, ...]: ...


def validate_query(query: str) -> str:
    normalized = query.strip()
    if (
        not normalized
        or len(normalized) > MAX_QUERY_CHARS
        or len(normalized.encode("utf-8")) > MAX_QUERY_BYTES
        or "\x00" in normalized
    ):
        raise ValueError("retrieval query is outside the bounded contract")
    return normalized
