"""Offline semantic-model adapters."""

from adapters.semantic.huggingface import (
    EncodedSemanticBatch,
    OfflineSemanticEncoder,
    SemanticModelUnavailableError,
)

__all__ = [
    "EncodedSemanticBatch",
    "OfflineSemanticEncoder",
    "SemanticModelUnavailableError",
]
