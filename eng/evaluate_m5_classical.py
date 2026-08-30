#!/usr/bin/env python3
"""Generate/check the frozen synthetic M5 classical-model artifact."""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import cast

from eng.evaluate_m4_baseline import DEFAULT_OUTPUT as M4_ARTIFACT_PATH
from eng.evaluate_m4_baseline import build_fixture_dataset
from packages.ml_core import NUMERIC_REPRODUCIBILITY_TOLERANCE, train_classical_models

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "models" / "public" / "m5_classical_ml_v1.json"


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{path.name} must contain a JSON object")
    return cast(dict[str, object], value)


def _m4_extraction_commit() -> str:
    artifact = _json_object(M4_ARTIFACT_PATH)
    dataset = artifact.get("dataset")
    manifest = dataset.get("manifest") if isinstance(dataset, dict) else None
    commit = manifest.get("extraction_code_commit") if isinstance(manifest, dict) else None
    if not isinstance(commit, str):
        raise ValueError("M4 artifact does not name its extraction code commit")
    return commit


def build_artifact(*, training_code_commit: str) -> dict[str, object]:
    dataset = build_fixture_dataset(extraction_code_commit=_m4_extraction_commit())
    return train_classical_models(dataset, training_code_commit=training_code_commit)


def _serialized(value: dict[str, object]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def _stored_training_commit(artifact: dict[str, object]) -> str:
    value = artifact.get("training_code_commit")
    if not isinstance(value, str):
        raise ValueError("stored M5 artifact does not name its training code commit")
    return value


def _comparison_payload(artifact: dict[str, object]) -> dict[str, object]:
    """Remove exact native serialization/environment fields before tolerance comparison."""
    value = copy.deepcopy(artifact)
    value.pop("artifact_hash", None)
    preprocessing = value.get("preprocessing")
    if isinstance(preprocessing, dict):
        preprocessing.pop("preprocessor_hash", None)
    selection = value.get("active_selection")
    if isinstance(selection, dict):
        selection.pop("candidate_artifacts", None)
    reproducibility = value.get("reproducibility")
    if isinstance(reproducibility, dict):
        reproducibility.pop("recorded_environment", None)
    models = value.get("models")
    if isinstance(models, dict):
        for model in models.values():
            if not isinstance(model, dict):
                continue
            model.pop("artifact_hash", None)
            model.pop("preprocessor_hash", None)
            model.pop("booster_json_base64", None)
            model.pop("booster_json_sha256", None)
    return value


def _equivalent(expected: object, actual: object, *, path: str = "artifact") -> str | None:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return None if expected is actual else f"{path}: boolean mismatch"
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if math.isclose(
            float(expected),
            float(actual),
            rel_tol=0.0,
            abs_tol=NUMERIC_REPRODUCIBILITY_TOLERANCE,
        ):
            return None
        return f"{path}: numeric mismatch {expected!r} != {actual!r}"
    if isinstance(expected, dict) and isinstance(actual, dict):
        if set(expected) != set(actual):
            return f"{path}: object keys differ"
        for key in sorted(expected):
            mismatch = _equivalent(expected[key], actual[key], path=f"{path}.{key}")
            if mismatch:
                return mismatch
        return None
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return f"{path}: list lengths differ"
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual, strict=True)):
            mismatch = _equivalent(expected_item, actual_item, path=f"{path}[{index}]")
            if mismatch:
                return mismatch
        return None
    return None if expected == actual else f"{path}: {expected!r} != {actual!r}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code-commit")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.check:
        if not output.is_file():
            print(f"M5 model artifact is missing: {output}")
            return 1
        stored = _json_object(output)
        rebuilt = build_artifact(training_code_commit=_stored_training_commit(stored))
        if _serialized(stored) == _serialized(rebuilt):
            print("M5 model artifact is byte-reproducible")
            return 0
        mismatch = _equivalent(_comparison_payload(stored), _comparison_payload(rebuilt))
        if mismatch:
            print(f"M5 model artifact is outside its frozen tolerance: {mismatch}")
            return 1
        print(
            "M5 model artifact is reproducible within absolute tolerance "
            f"{NUMERIC_REPRODUCIBILITY_TOLERANCE:g}"
        )
        return 0
    if args.code_commit is None:
        parser.error("--code-commit is required when generating an artifact")
    artifact = build_artifact(training_code_commit=args.code_commit)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_serialized(artifact), encoding="utf-8", newline="\n")
    print(f"wrote {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
