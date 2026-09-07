"""Bounded reader for the source-controlled M13 governance evaluation registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from django.conf import settings

from packages.change_intel import canonical_hash

MAX_GOVERNANCE_ARTIFACT_BYTES = 500_000


def load_governance_artifact(path: Path | None = None) -> dict[str, object]:
    artifact_path = path or Path(settings.M13_GOVERNANCE_ARTIFACT_PATH)
    try:
        size = artifact_path.stat().st_size
        value = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("governance artifact is unavailable or invalid") from error
    if not 2 <= size <= MAX_GOVERNANCE_ARTIFACT_BYTES or not isinstance(value, dict):
        raise ValueError("governance artifact size or shape is invalid")
    artifact = cast(dict[str, object], value)
    if set(artifact) != {
        "drift",
        "evaluation_registry",
        "feedback",
        "formal_experiments",
        "limitations",
        "mlflow",
        "model_registry",
        "rollback_drill",
        "root_sha256",
        "schema_version",
        "synthetic",
    }:
        raise ValueError("governance artifact shape is invalid")
    root_sha256 = artifact.get("root_sha256")
    unhashed = {key: item for key, item in artifact.items() if key != "root_sha256"}
    if (
        artifact.get("schema_version") != "m13-governance-evaluation-v1"
        or artifact.get("synthetic") is not True
        or root_sha256 != canonical_hash(unhashed)
    ):
        raise ValueError("governance artifact identity or checksum is invalid")
    entries = artifact.get("evaluation_registry")
    if not isinstance(entries, list) or len(entries) != 3:
        raise ValueError("governance evaluation registry is incomplete")
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("contains_customer_code") is not False:
            raise ValueError("governance evaluation registry contains unsafe data")
    experiments = artifact.get("formal_experiments")
    if not isinstance(experiments, list) or len(experiments) != 3:
        raise ValueError("governance formal experiment registry is incomplete")
    for experiment in experiments:
        if (
            not isinstance(experiment, dict)
            or experiment.get("contains_customer_code") is not False
            or experiment.get("data_scope") not in {"public_synthetic", "public_approved"}
        ):
            raise ValueError("governance formal experiment registry contains unsafe data")
    limitations = artifact.get("limitations")
    if (
        not isinstance(limitations, list)
        or not 1 <= len(limitations) <= 16
        or not all(isinstance(item, str) and len(item) <= 512 for item in limitations)
    ):
        raise ValueError("governance artifact limitations are invalid")
    return artifact


def latest_evaluations_summary(path: Path | None = None) -> dict[str, object]:
    artifact = load_governance_artifact(path)
    return {
        "evaluation_registry": artifact["evaluation_registry"],
        "formal_experiments": artifact["formal_experiments"],
        "limitations": artifact["limitations"],
        "model_registry": artifact["model_registry"],
        "root_sha256": artifact["root_sha256"],
        "schema_version": artifact["schema_version"],
        "synthetic": True,
    }
