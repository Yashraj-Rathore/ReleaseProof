"""Network-free deterministic embedding and reranking fakes for tests and demos."""

from __future__ import annotations

import hashlib
import math

from packages.retrieval_core import ModelArtifact
from packages.retrieval_core.normalization import code_tokens, lexical_score

FAKE_EMBEDDING_DIMENSION = 384


class DeterministicEmbeddingProvider:
    adapter_version = "deterministic-hash-embedding-adapter-v1"

    def __init__(
        self, *, version: str = "deterministic-hash-embedding-v1", salt: str = "v1"
    ) -> None:
        self._salt = salt
        checksum = hashlib.sha256(f"{version}:{salt}".encode()).hexdigest()
        self._artifact = ModelArtifact(
            version=version,
            model_id="releaseproof-fixture/deterministic-hash-embedding",
            revision="0" * 40,
            safetensors_sha256=checksum,
            license="synthetic-test-fixture",
            dimension=FAKE_EMBEDDING_DIMENSION,
        )

    @property
    def artifact(self) -> ModelArtifact:
        return self._artifact

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        return tuple(self._embed_one(text) for text in texts)

    def _embed_one(self, text: str) -> tuple[float, ...]:
        values = [0.0] * FAKE_EMBEDDING_DIMENSION
        for token in code_tokens(text):
            digest = hashlib.sha256(f"{self._salt}:{token}".encode()).digest()
            bucket = int.from_bytes(digest[:2], "big") % FAKE_EMBEDDING_DIMENSION
            sign = 1.0 if digest[2] & 1 else -1.0
            values[bucket] += sign
        norm = math.sqrt(sum(value * value for value in values))
        if norm:
            values = [value / norm for value in values]
        return tuple(values)


class DeterministicReranker:
    adapter_version = "deterministic-lexical-reranker-adapter-v1"

    def __init__(self) -> None:
        self._artifact = ModelArtifact(
            version="deterministic-lexical-reranker-v1",
            model_id="releaseproof-fixture/deterministic-lexical-reranker",
            revision="0" * 40,
            safetensors_sha256=hashlib.sha256(b"deterministic-lexical-reranker-v1").hexdigest(),
            license="synthetic-test-fixture",
        )

    @property
    def artifact(self) -> ModelArtifact:
        return self._artifact

    def score(self, query: str, documents: tuple[str, ...]) -> tuple[float, ...]:
        return tuple(float(lexical_score(query, document)) for document in documents)
