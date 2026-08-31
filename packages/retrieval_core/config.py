"""Immutable M6 retrieval configuration and selected public model artifacts."""

from __future__ import annotations

from dataclasses import dataclass

RETRIEVAL_SCHEMA_VERSION = "retrieval-result-v1"
RETRIEVAL_EVALUATION_VERSION = "m6-retrieval-eval-v1"
CHUNKING_VERSION = "source-aware-chunker-v1"
NORMALIZER_VERSION = "code-aware-normalizer-v1"
FTS_CONFIGURATION = "simple"
FTS_PROFILE_VERSION = "postgres-simple-code-v1"
FUSION_VERSION = "rrf-v1-k60"
RERANKER_VERSION = "ms-marco-minilm-l6-v2-4bebbd5-v1"


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    """Exact immutable Hugging Face artifact identity used by an adapter."""

    version: str
    model_id: str
    revision: str
    safetensors_sha256: str
    license: str
    dimension: int | None = None

    def __post_init__(self) -> None:
        if not self.version or not self.model_id:
            raise ValueError("model artifact identity is required")
        if len(self.revision) != 40 or any(
            character not in "0123456789abcdef" for character in self.revision
        ):
            raise ValueError("model revision must be an exact lowercase Git commit")
        if len(self.safetensors_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.safetensors_sha256
        ):
            raise ValueError("model artifact checksum must be lowercase SHA-256")
        if self.dimension is not None and self.dimension < 1:
            raise ValueError("embedding dimension must be positive")


EMBEDDING_ARTIFACT = ModelArtifact(
    version="all-minilm-l6-v2-1110a24-v1",
    model_id="sentence-transformers/all-MiniLM-L6-v2",
    revision="1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
    safetensors_sha256="53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db",
    license="Apache-2.0",
    dimension=384,
)

RERANKER_ARTIFACT = ModelArtifact(
    version=RERANKER_VERSION,
    model_id="cross-encoder/ms-marco-MiniLM-L6-v2",
    revision="4bebbd56fc380a66525f95b03d4ec1a4b41a4f1e",
    safetensors_sha256="821d1aa69520101d6e0737f78a042ae25b19e5cb9160701909d10434f4aeb0ae",
    license="Apache-2.0",
)
