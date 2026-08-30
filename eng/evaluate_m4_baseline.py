#!/usr/bin/env python3
"""Rebuild/check the frozen synthetic M4 dataset and heuristic evidence artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import cast

from packages.dataset_core import (
    DatasetBuild,
    TemporalSplitPolicy,
    build_dataset,
    extract_approved_source,
    parse_source_admission,
)
from packages.ml_core import evaluate_baseline

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "datasets"
ADMISSION_PATH = FIXTURE_DIR / "m4_source_admission.json"
SNAPSHOTS_PATH = FIXTURE_DIR / "m4_snapshots.json"
LICENSE_PATH = ROOT / "tests" / "fixtures" / "repositories" / "releaseproof_fixture" / "LICENSE"
DEFAULT_OUTPUT = ROOT / "artifacts" / "evaluation" / "m4_synthetic_baseline_v1.json"
DATASET_VERSION = "releaseproof-m4-synthetic-v1"


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{path.name} must contain a JSON object")
    return cast(dict[str, object], value)


def build_fixture_dataset(*, extraction_code_commit: str) -> DatasetBuild:
    admission = parse_source_admission(_json_object(ADMISSION_PATH))
    actual_license_hash = hashlib.sha256(LICENSE_PATH.read_bytes()).hexdigest()
    if actual_license_hash != admission.license_evidence_sha256:
        raise ValueError("fixture license evidence hash does not match the admission record")
    extracted = extract_approved_source(
        admission=admission,
        payload=_json_object(SNAPSHOTS_PATH),
    )
    policy = TemporalSplitPolicy(
        train_before=datetime.fromisoformat("2024-07-01T00:00:00+00:00"),
        validation_before=datetime.fromisoformat("2024-11-01T00:00:00+00:00"),
        test_before=datetime.fromisoformat("2025-04-01T00:00:00+00:00"),
    )
    return build_dataset(
        dataset_version=DATASET_VERSION,
        source=extracted,
        split_policy=policy,
        extraction_code_commit=extraction_code_commit,
    )


def build_artifact(*, extraction_code_commit: str) -> dict[str, object]:
    dataset = build_fixture_dataset(extraction_code_commit=extraction_code_commit)
    return {
        "artifact_schema_version": "m4-synthetic-evidence-v1",
        "dataset": dataset.as_dict(),
        "evaluation": evaluate_baseline(dataset),
    }


def _serialized(value: dict[str, object]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    expected = _serialized(build_artifact(extraction_code_commit=args.code_commit))
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != expected:
            print(f"M4 evidence artifact is stale: {output}")
            return 1
        print("M4 evidence artifact is reproducible")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(expected, encoding="utf-8", newline="\n")
    print(f"wrote {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
