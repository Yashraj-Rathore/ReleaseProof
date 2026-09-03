"""Checksum-verified, local-files-only Hugging Face semantic encoder."""

from __future__ import annotations

import hashlib
import importlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.dataset_core import MAX_SEMANTIC_TEXT_BYTES
from packages.retrieval_core import EMBEDDING_ARTIFACT

SEMANTIC_ENCODER_ADAPTER_VERSION = "hf-semantic-encoder-v1"
SEMANTIC_MAX_TOKENS = 256
SEMANTIC_EMBEDDING_DIMENSION = 384
MAX_ENCODER_BATCH_ROWS = 10_000


class SemanticModelUnavailableError(RuntimeError):
    """The exact local model is absent, incompatible, or invalid."""


@dataclass(frozen=True, slots=True)
class EncodedSemanticBatch:
    vectors: tuple[tuple[float, ...], ...]
    token_counts: tuple[int, ...]
    truncated: tuple[bool, ...]


def _verified_model_path(cache_path: Path) -> Path:
    resolved = cache_path.resolve()
    if not resolved.is_dir():
        raise SemanticModelUnavailableError("semantic model cache is unavailable")
    weights = resolved / "model.safetensors"
    if not weights.is_file():
        raise SemanticModelUnavailableError("semantic model safetensors file is unavailable")
    checksum = hashlib.sha256(weights.read_bytes()).hexdigest()
    if checksum != EMBEDDING_ARTIFACT.safetensors_sha256:
        raise SemanticModelUnavailableError("semantic model safetensors checksum mismatch")
    required_files = {
        "config.json",
        "modules.json",
        "sentence_bert_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
    }
    if any(not (resolved / name).is_file() for name in required_files):
        raise SemanticModelUnavailableError("semantic model cache is incomplete")
    return resolved


class OfflineSemanticEncoder:
    """Use the approved MiniLM revision without network access or remote code."""

    adapter_version = SEMANTIC_ENCODER_ADAPTER_VERSION

    def __init__(self, *, cache_path: Path) -> None:
        self._path = _verified_model_path(cache_path)
        self._model: Any | None = None
        self._tokenizer: Any | None = None

    @property
    def model_path(self) -> Path:
        return self._path

    def _load(self) -> tuple[Any, Any]:
        if self._model is None or self._tokenizer is None:
            try:
                sentence_transformers = importlib.import_module("sentence_transformers")
                transformers = importlib.import_module("transformers")
                self._model = sentence_transformers.SentenceTransformer(
                    str(self._path),
                    device="cpu",
                    local_files_only=True,
                    trust_remote_code=False,
                    model_kwargs={"use_safetensors": True},
                )
                self._model.max_seq_length = SEMANTIC_MAX_TOKENS
                self._tokenizer = transformers.AutoTokenizer.from_pretrained(
                    str(self._path),
                    local_files_only=True,
                    trust_remote_code=False,
                )
            except (AttributeError, ImportError, OSError, RuntimeError, ValueError) as error:
                raise SemanticModelUnavailableError(
                    "semantic encoder could not be loaded from the verified offline cache"
                ) from error
        return self._model, self._tokenizer

    def encode(self, texts: tuple[str, ...]) -> EncodedSemanticBatch:
        if not texts or len(texts) > MAX_ENCODER_BATCH_ROWS:
            raise ValueError("semantic encoder input must be a non-empty bounded batch")
        if any(len(text.encode("utf-8")) > MAX_SEMANTIC_TEXT_BYTES for text in texts):
            raise ValueError("semantic encoder text exceeds the dataset byte bound")
        model, tokenizer = self._load()
        token_counts: list[int] = []
        for text in texts:
            token_ids = tokenizer.encode(text, add_special_tokens=True, truncation=False)
            if not isinstance(token_ids, list) or not all(
                isinstance(item, int) for item in token_ids
            ):
                raise SemanticModelUnavailableError("semantic tokenizer returned invalid token IDs")
            token_counts.append(len(token_ids))
        encoded = model.encode(
            list(texts),
            batch_size=min(16, len(texts)),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors = tuple(tuple(float(value) for value in row) for row in encoded)
        if len(vectors) != len(texts) or any(
            len(vector) != SEMANTIC_EMBEDDING_DIMENSION
            or any(not math.isfinite(value) for value in vector)
            for vector in vectors
        ):
            raise SemanticModelUnavailableError("semantic encoder returned incompatible embeddings")
        return EncodedSemanticBatch(
            vectors=vectors,
            token_counts=tuple(token_counts),
            truncated=tuple(count > SEMANTIC_MAX_TOKENS for count in token_counts),
        )
