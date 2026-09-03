"""Build or verify the frozen M11 semantic-model experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
import time
from pathlib import Path
from typing import cast

from adapters.semantic import OfflineSemanticEncoder
from eng.evaluate_m4_baseline import (
    ADMISSION_PATH,
    LICENSE_PATH,
    SNAPSHOTS_PATH,
    build_fixture_dataset,
)
from packages.change_intel import canonical_hash
from packages.dataset_core import (
    DatasetSplit,
    SemanticDataset,
    build_semantic_dataset,
    extract_approved_source,
    parse_semantic_annotations,
    parse_source_admission,
)
from packages.ml_core.semantic import (
    NUMERIC_REPRODUCIBILITY_TOLERANCE,
    SEMANTIC_EMBEDDING_SCHEMA_VERSION,
    train_semantic_experiment,
    validate_frozen_embeddings,
    validate_semantic_model_artifact,
)
from packages.retrieval_core import EMBEDDING_ARTIFACT

ROOT = Path(__file__).resolve().parents[1]
ANNOTATION_PATH = ROOT / "tests" / "fixtures" / "datasets" / "m11_semantic_annotations.json"
M4_ARTIFACT_PATH = ROOT / "tests" / "golden" / "m4_synthetic_baseline_v1.json"
M5_ARTIFACT_PATH = ROOT / "models" / "public" / "m5_classical_ml_v1.json"
DATASET_PATH = ROOT / "datasets" / "public" / "m11_semantic_dataset_v1.json"
EMBEDDING_PATH = ROOT / "artifacts" / "evaluation" / "m11_minilm_embeddings_v1.json"
MODEL_PATH = ROOT / "models" / "public" / "m11_semantic_head_v1.json"
EVALUATION_PATH = ROOT / "artifacts" / "evaluation" / "m11_semantic_eval_v1.json"
LATENCY_REPETITIONS = 10


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{path.name} must contain a JSON object")
    return cast(dict[str, object], value)


def _serialized(value: dict[str, object]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def _number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    return float(value)


def _m4_extraction_commit() -> str:
    artifact = _json_object(M4_ARTIFACT_PATH)
    dataset = artifact.get("dataset")
    manifest = dataset.get("manifest") if isinstance(dataset, dict) else None
    commit = manifest.get("extraction_code_commit") if isinstance(manifest, dict) else None
    if not isinstance(commit, str):
        raise ValueError("M4 artifact does not name its extraction code commit")
    return commit


def build_semantic_fixture() -> SemanticDataset:
    source_dataset = build_fixture_dataset(extraction_code_commit=_m4_extraction_commit())
    admission = parse_source_admission(_json_object(ADMISSION_PATH))
    if hashlib.sha256(LICENSE_PATH.read_bytes()).hexdigest() != admission.license_evidence_sha256:
        raise ValueError("fixture license evidence does not match the M4 admission")
    source = extract_approved_source(admission=admission, payload=_json_object(SNAPSHOTS_PATH))
    annotations = parse_semantic_annotations(_json_object(ANNOTATION_PATH))
    return build_semantic_dataset(
        source_dataset=source_dataset,
        extracted_source=source,
        annotations=annotations,
    )


def _whitespace_variant(text: str) -> str:
    return " ".join(text.split())


def _vector_payload(
    *, vector: tuple[float, ...], token_count: int, truncated: bool, text_sha256: str
) -> dict[str, object]:
    rounded = [round(float(value), 10) for value in vector]
    return {
        "text_sha256": text_sha256,
        "token_count": token_count,
        "truncated": truncated,
        "vector": rounded,
        "vector_sha256": canonical_hash(rounded),
    }


def build_embedding_artifact(dataset: SemanticDataset, *, model_dir: Path) -> dict[str, object]:
    encoder = OfflineSemanticEncoder(cache_path=model_dir)
    texts = tuple(row.text for row in dataset.rows)
    variants = tuple(_whitespace_variant(row.text) for row in dataset.rows)
    original = encoder.encode(texts)
    whitespace = encoder.encode(variants)
    latency_samples: list[float] = []
    for _index in range(LATENCY_REPETITIONS):
        started = time.perf_counter_ns()
        encoder.encode(texts)
        latency_samples.append((time.perf_counter_ns() - started) / 1_000_000.0)
    file_hashes = {
        path.relative_to(model_dir.resolve()).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(model_dir.resolve().rglob("*"))
        if path.is_file() and ".cache" not in path.parts
    }
    rows: list[dict[str, object]] = []
    for index, row in enumerate(dataset.rows):
        variant = variants[index]
        rows.append(
            {
                "original": _vector_payload(
                    vector=original.vectors[index],
                    token_count=original.token_counts[index],
                    truncated=original.truncated[index],
                    text_sha256=row.text_sha256,
                ),
                "snapshot_id": row.snapshot_id,
                "whitespace_variant": _vector_payload(
                    vector=whitespace.vectors[index],
                    token_count=whitespace.token_counts[index],
                    truncated=whitespace.truncated[index],
                    text_sha256=canonical_hash(
                        {"text": variant, "variant": "collapse-whitespace-v1"}
                    ),
                ),
            }
        )
    ordered = sorted(latency_samples)
    stable: dict[str, object] = {
        "dataset_manifest_sha256": dataset.manifest_sha256,
        "encoder": {
            "adapter_version": encoder.adapter_version,
            "dimension": EMBEDDING_ARTIFACT.dimension,
            "license": EMBEDDING_ARTIFACT.license,
            "max_tokens": 256,
            "model_id": EMBEDDING_ARTIFACT.model_id,
            "revision": EMBEDDING_ARTIFACT.revision,
            "safetensors_sha256": EMBEDDING_ARTIFACT.safetensors_sha256,
        },
        "generation": {
            "environment": {
                "machine": platform.machine() or "not reported",
                "platform": platform.platform(),
                "python": platform.python_version(),
                "processor": platform.processor() or "not reported",
            },
            "latency": {
                "batch_rows": len(texts),
                "cold_model_load_excluded": True,
                "median_batch_ms": round(statistics.median(latency_samples), 6),
                "minimum_batch_ms": round(min(latency_samples), 6),
                "p95_batch_ms": round(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))], 6),
                "repetitions": LATENCY_REPETITIONS,
            },
            "model_files_sha256": file_hashes,
            "network_during_inference": False,
            "weights_provisioned_explicitly": True,
        },
        "rows": rows,
        "schema_version": SEMANTIC_EMBEDDING_SCHEMA_VERSION,
        "synthetic": True,
    }
    return {**stable, "root_sha256": canonical_hash(stable)}


def _risk_comparison() -> dict[str, object]:
    m4 = _json_object(M4_ARTIFACT_PATH)
    m5 = _json_object(M5_ARTIFACT_PATH)
    m4_evaluation = cast(dict[str, object], m4["evaluation"])
    m4_rows = cast(list[dict[str, object]], m4_evaluation["raw_predictions"])
    heuristic = {
        str(item["snapshot_id"]): item
        for item in m4_rows
        if item.get("split") == DatasetSplit.TEST.value
    }
    models = cast(dict[str, object], m5["models"])
    boosted = cast(dict[str, object], models["xgboost-risk-v1"])
    boosted_rows = {
        str(item["snapshot_id"]): item
        for item in cast(list[dict[str, object]], boosted["raw_test_predictions"])
    }
    rows = []
    for snapshot_id in sorted(heuristic):
        heuristic_row = heuristic[snapshot_id]
        boosted_row = boosted_rows[snapshot_id]
        rows.append(
            {
                "heuristic_score": _number(heuristic_row["score"], field="heuristic score") / 100.0,
                "proxy_positive": heuristic_row["actual_proxy_label"] == "proxy_positive",
                "snapshot_id": snapshot_id,
                "xgboost_score": boosted_row["model_score"],
            }
        )
    return {
        "rows": rows,
        "source_artifacts": {
            "m4_evaluation_sha256": m4_evaluation["evaluation_hash"],
            "m5_artifact_sha256": m5["artifact_hash"],
            "m5_xgboost_artifact_sha256": boosted["artifact_hash"],
        },
    }


def build_experiment(
    dataset: SemanticDataset,
    embedding_artifact: dict[str, object],
    *,
    training_code_commit: str,
) -> tuple[dict[str, object], dict[str, object]]:
    return train_semantic_experiment(
        dataset,
        embedding_artifact,
        training_code_commit=training_code_commit,
        risk_comparison=_risk_comparison(),
    )


def _without_hashes(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_hashes(item)
            for key, item in value.items()
            if not key.endswith("sha256") and key not in {"state_sha256"}
        }
    if isinstance(value, list):
        return [_without_hashes(item) for item in value]
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


def _write(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_serialized(value), encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT)}")


def _verify() -> None:
    dataset = build_semantic_fixture()
    committed_dataset = _json_object(DATASET_PATH)
    if committed_dataset != dataset.as_dict():
        raise ValueError("committed M11 semantic dataset is stale")
    embeddings = _json_object(EMBEDDING_PATH)
    validate_frozen_embeddings(embeddings, dataset=dataset)
    committed_model = _json_object(MODEL_PATH)
    validate_semantic_model_artifact(committed_model)
    committed_evaluation = _json_object(EVALUATION_PATH)
    root_hash = committed_evaluation.get("root_sha256")
    evaluation_payload = {
        key: value for key, value in committed_evaluation.items() if key != "root_sha256"
    }
    if root_hash != canonical_hash(evaluation_payload):
        raise ValueError("committed M11 evaluation checksum is invalid")
    training_commit = committed_model.get("training_code_commit")
    if not isinstance(training_commit, str):
        raise ValueError("committed M11 model is missing its training commit")
    rebuilt_model, rebuilt_evaluation = build_experiment(
        dataset, embeddings, training_code_commit=training_commit
    )
    model_mismatch = _equivalent(
        _without_hashes(committed_model), _without_hashes(rebuilt_model), path="model"
    )
    if model_mismatch:
        raise ValueError(f"M11 model is outside its frozen tolerance: {model_mismatch}")
    evaluation_mismatch = _equivalent(
        _without_hashes(committed_evaluation),
        _without_hashes(rebuilt_evaluation),
        path="evaluation",
    )
    if evaluation_mismatch:
        raise ValueError(f"M11 evaluation is outside its frozen tolerance: {evaluation_mismatch}")
    print(
        json.dumps(
            {
                "dataset_manifest_sha256": dataset.manifest_sha256,
                "held_out_metrics": cast(dict[str, object], committed_evaluation["held_out"])[
                    "metrics"
                ],
                "incremental_decision": cast(
                    dict[str, object], committed_evaluation["incremental_value"]
                )["decision"],
                "status": "verified",
            },
            indent=2,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--code-commit")
    parser.add_argument("--model-dir", type=Path)
    args = parser.parse_args()
    if args.check == args.write:
        parser.error("choose exactly one of --check or --write")
    if args.check:
        _verify()
        return 0
    if args.code_commit is None:
        parser.error("--code-commit is required when writing M11 artifacts")
    dataset = build_semantic_fixture()
    if args.model_dir is not None:
        embeddings = build_embedding_artifact(dataset, model_dir=args.model_dir.resolve())
        _write(EMBEDDING_PATH, embeddings)
    else:
        embeddings = _json_object(EMBEDDING_PATH)
    validate_frozen_embeddings(embeddings, dataset=dataset)
    model, evaluation = build_experiment(dataset, embeddings, training_code_commit=args.code_commit)
    _write(DATASET_PATH, dataset.as_dict())
    _write(MODEL_PATH, model)
    _write(EVALUATION_PATH, evaluation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
