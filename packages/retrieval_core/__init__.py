"""Framework-light retrieval, chunking, fusion, and evaluation contracts."""

from packages.retrieval_core.chunking import chunk_document
from packages.retrieval_core.config import (
    CHUNKING_VERSION,
    EMBEDDING_ARTIFACT,
    FTS_CONFIGURATION,
    FTS_PROFILE_VERSION,
    FUSION_VERSION,
    NORMALIZER_VERSION,
    RERANKER_ARTIFACT,
    RERANKER_VERSION,
    RETRIEVAL_EVALUATION_VERSION,
    RETRIEVAL_SCHEMA_VERSION,
    ModelArtifact,
)
from packages.retrieval_core.contracts import (
    ChunkCandidate,
    EmbeddingProvider,
    EvidenceDocumentInput,
    EvidenceSourceType,
    IndexLifecycle,
    RerankerProvider,
    RetrievalHit,
    SourceChunk,
)
from packages.retrieval_core.evaluation import EvaluationCase, evaluate_rankings
from packages.retrieval_core.fusion import reciprocal_rank_fusion, rerank_candidates
from packages.retrieval_core.normalization import (
    cosine_similarity,
    lexical_score,
    normalize_fts_text,
    normalize_source_text,
)

__all__ = [
    "CHUNKING_VERSION",
    "EMBEDDING_ARTIFACT",
    "FTS_CONFIGURATION",
    "FTS_PROFILE_VERSION",
    "FUSION_VERSION",
    "NORMALIZER_VERSION",
    "RERANKER_ARTIFACT",
    "RERANKER_VERSION",
    "RETRIEVAL_EVALUATION_VERSION",
    "RETRIEVAL_SCHEMA_VERSION",
    "ChunkCandidate",
    "EmbeddingProvider",
    "EvaluationCase",
    "EvidenceDocumentInput",
    "EvidenceSourceType",
    "IndexLifecycle",
    "ModelArtifact",
    "RerankerProvider",
    "RetrievalHit",
    "SourceChunk",
    "chunk_document",
    "cosine_similarity",
    "evaluate_rankings",
    "lexical_score",
    "normalize_fts_text",
    "normalize_source_text",
    "reciprocal_rank_fusion",
    "rerank_candidates",
]
