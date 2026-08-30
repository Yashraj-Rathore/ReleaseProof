"""Bounded adapter for the committed public M5 model artifact."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from django.conf import settings

from packages.ml_core import (
    BASELINE_ARTIFACT_VERSION,
    ModelCompatibilityError,
    baseline_artifact_hash,
    current_model_summary,
    validate_classical_artifact,
)

MAX_PUBLIC_MODEL_ARTIFACT_BYTES = 2_000_000


def load_public_model_artifact(path: Path | None = None) -> dict[str, object]:
    artifact_path = path or Path(settings.M5_CLASSICAL_ARTIFACT_PATH)
    try:
        size = artifact_path.stat().st_size
    except OSError as error:
        raise ModelCompatibilityError("configured public model artifact is unavailable") from error
    if size < 2 or size > MAX_PUBLIC_MODEL_ARTIFACT_BYTES:
        raise ModelCompatibilityError("configured public model artifact size is invalid")
    try:
        value = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ModelCompatibilityError("configured public model artifact is invalid") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ModelCompatibilityError("configured public model artifact must be an object")
    artifact = cast(dict[str, object], value)
    validate_classical_artifact(artifact)
    return artifact


def safe_current_model_summary(path: Path | None = None) -> dict[str, object]:
    try:
        return current_model_summary(load_public_model_artifact(path))
    except ModelCompatibilityError:
        return {
            "active": {
                "artifact_hash": baseline_artifact_hash(),
                "artifact_version": BASELINE_ARTIFACT_VERSION,
                "decision": "fallback_model_artifact_unavailable",
                "probability_display_allowed": False,
                "reasons": [
                    "The learned-model artifact is unavailable or invalid; deterministic evidence "
                    "remains active."
                ],
            },
            "candidates": [],
            "dataset": None,
            "evaluation_artifact_hash": None,
            "limitations": ["Learned-model evidence is currently unavailable."],
            "model_card_version": None,
        }
