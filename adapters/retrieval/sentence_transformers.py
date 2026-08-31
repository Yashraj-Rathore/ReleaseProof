"""Offline-only exact-artifact sentence-transformers adapters."""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
from typing import Any

from packages.retrieval_core import EMBEDDING_ARTIFACT, RERANKER_ARTIFACT, ModelArtifact


class LocalModelUnavailableError(RuntimeError):
    """Raised when an explicitly provisioned immutable model cache is unavailable or invalid."""


def _verified_model_path(cache_path: Path, artifact: ModelArtifact) -> Path:
    resolved = cache_path.resolve()
    if not resolved.is_dir():
        raise LocalModelUnavailableError(f"local model cache is unavailable for {artifact.version}")
    weights = resolved / "model.safetensors"
    if not weights.is_file():
        raise LocalModelUnavailableError(
            f"safetensors artifact is unavailable for {artifact.version}"
        )
    checksum = hashlib.sha256(weights.read_bytes()).hexdigest()
    if checksum != artifact.safetensors_sha256:
        raise LocalModelUnavailableError(f"safetensors checksum mismatch for {artifact.version}")
    return resolved


class SentenceTransformerEmbeddingProvider:
    adapter_version = "sentence-transformers-embedding-adapter-v1"

    def __init__(self, *, cache_path: Path) -> None:
        self._path = _verified_model_path(cache_path, EMBEDDING_ARTIFACT)
        self._model: Any | None = None

    @property
    def artifact(self) -> ModelArtifact:
        return EMBEDDING_ARTIFACT

    def _load(self) -> Any:
        if self._model is None:
            try:
                package = importlib.import_module("sentence_transformers")
                self._model = package.SentenceTransformer(
                    str(self._path),
                    local_files_only=True,
                    trust_remote_code=False,
                    model_kwargs={"use_safetensors": True},
                )
            except (ImportError, OSError, RuntimeError, ValueError) as error:
                raise LocalModelUnavailableError(
                    "embedding model could not be loaded offline"
                ) from error
        return self._model

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        model = self._load()
        encoded = model.encode(
            list(texts),
            batch_size=min(32, len(texts)),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors = tuple(tuple(float(value) for value in row) for row in encoded)
        if any(len(vector) != EMBEDDING_ARTIFACT.dimension for vector in vectors):
            raise LocalModelUnavailableError("embedding model returned an incompatible dimension")
        return vectors


class SentenceTransformerReranker:
    adapter_version = "sentence-transformers-reranker-adapter-v1"

    def __init__(self, *, cache_path: Path) -> None:
        self._path = _verified_model_path(cache_path, RERANKER_ARTIFACT)
        self._model: Any | None = None

    @property
    def artifact(self) -> ModelArtifact:
        return RERANKER_ARTIFACT

    def _load(self) -> Any:
        if self._model is None:
            try:
                package = importlib.import_module("sentence_transformers")
                self._model = package.CrossEncoder(
                    str(self._path),
                    local_files_only=True,
                    trust_remote_code=False,
                    model_kwargs={"use_safetensors": True},
                )
            except (ImportError, OSError, RuntimeError, ValueError) as error:
                raise LocalModelUnavailableError(
                    "reranker model could not be loaded offline"
                ) from error
        return self._model

    def score(self, query: str, documents: tuple[str, ...]) -> tuple[float, ...]:
        if not documents:
            return ()
        model = self._load()
        scores = model.predict(
            [(query, document) for document in documents],
            batch_size=min(16, len(documents)),
            show_progress_bar=False,
        )
        return tuple(float(score) for score in scores)
