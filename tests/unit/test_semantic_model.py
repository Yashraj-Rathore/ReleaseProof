from __future__ import annotations

import copy
import hashlib
import json

import pytest

from adapters.semantic import OfflineSemanticEncoder, SemanticModelUnavailableError
from eng.evaluate_m4_baseline import ADMISSION_PATH, SNAPSHOTS_PATH, build_fixture_dataset
from eng.evaluate_m11_semantic import (
    ANNOTATION_PATH,
    build_semantic_fixture,
)
from packages.change_intel import canonical_hash
from packages.dataset_core import (
    DatasetSplit,
    SemanticDatasetError,
    build_semantic_dataset,
    extract_approved_source,
    parse_semantic_annotations,
    parse_source_admission,
)
from packages.ml_core.semantic import (
    SEMANTIC_EMBEDDING_SCHEMA_VERSION,
    SemanticModelError,
    score_semantic_embedding,
    train_semantic_experiment,
    validate_frozen_embeddings,
    validate_semantic_model_artifact,
)
from packages.retrieval_core import EMBEDDING_ARTIFACT


def _fake_embeddings() -> dict[str, object]:
    dataset = build_semantic_fixture()
    rows = []
    for row_index, row in enumerate(dataset.rows):
        digest = hashlib.sha256(row.snapshot_id.encode()).digest()
        vector = [float(value) for value in row.label_vector]
        vector.extend(
            ((digest[index % len(digest)] / 255.0) - 0.5) * 0.01
            for index in range(384 - len(vector))
        )
        vector = [round(value, 10) for value in vector]
        token_count = 10 + row_index
        item = {
            "text_sha256": row.text_sha256,
            "token_count": token_count,
            "truncated": False,
            "vector": vector,
            "vector_sha256": canonical_hash(vector),
        }
        rows.append(
            {
                "original": item,
                "snapshot_id": row.snapshot_id,
                "whitespace_variant": {
                    **item,
                    "text_sha256": canonical_hash(
                        {"snapshot_id": row.snapshot_id, "variant": "whitespace"}
                    ),
                },
            }
        )
    payload: dict[str, object] = {
        "dataset_manifest_sha256": dataset.manifest_sha256,
        "encoder": {
            "adapter_version": "hf-semantic-encoder-v1",
            "dimension": 384,
            "license": EMBEDDING_ARTIFACT.license,
            "max_tokens": 256,
            "model_id": EMBEDDING_ARTIFACT.model_id,
            "revision": EMBEDDING_ARTIFACT.revision,
            "safetensors_sha256": EMBEDDING_ARTIFACT.safetensors_sha256,
        },
        "generation": {"synthetic_fake_for_unit_test": True},
        "rows": rows,
        "schema_version": SEMANTIC_EMBEDDING_SCHEMA_VERSION,
        "synthetic": True,
    }
    return {**payload, "root_sha256": canonical_hash(payload)}


def _risk_comparison() -> dict[str, object]:
    return {
        "rows": [
            {
                "heuristic_score": score,
                "proxy_positive": expected,
                "snapshot_id": snapshot_id,
                "xgboost_score": boosted,
            }
            for snapshot_id, expected, score, boosted in (
                ("m4-011", True, 0.30, 0.259054631),
                ("m4-012", True, 0.35, 0.7409453988),
                ("m4-013", False, 0.50, 0.7409453988),
                ("m4-014", False, 0.35, 0.7409453988),
            )
        ],
        "source_artifacts": {"fixture": "unit-test"},
    }


def test_semantic_dataset_is_outcome_blind_bounded_and_inherits_frozen_split() -> None:
    first = build_semantic_fixture()
    second = build_semantic_fixture()

    assert first.as_dict() == second.as_dict()
    assert first.synthetic is True
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.counts["split_counts"] == {
        "excluded": 2,
        "test": 4,
        "train": 6,
        "validation": 4,
    }
    assert first.leakage_report["violations"] == []
    assert first.leakage_report["repository_holdout_measured"] is False
    assert all(row.text_bytes <= 4_096 for row in first.rows)
    assert all("proxy_positive" not in row.text for row in first.rows)
    assert all("outcome" not in row.text.casefold() for row in first.rows)
    assert {row.snapshot_id for row in first.rows if row.split is DatasetSplit.EXCLUDED} == {
        "m4-015",
        "m4-016",
    }


def test_semantic_annotation_and_source_lineage_tampering_fail_closed() -> None:
    raw = json.loads(ANNOTATION_PATH.read_text(encoding="utf-8"))
    not_blind = copy.deepcopy(raw)
    not_blind["outcome_blind"] = False
    with pytest.raises(SemanticDatasetError, match="outcome blind"):
        parse_semantic_annotations(not_blind)

    wrong_source = copy.deepcopy(raw)
    wrong_source["source_manifest_sha256"] = "0" * 64
    annotations = parse_semantic_annotations(wrong_source)
    dataset = build_semantic_fixture()
    source_dataset = build_fixture_dataset(
        extraction_code_commit="3448b1f879682d2b12a212d4c82d8fee87e33a12"
    )
    admission = parse_source_admission(json.loads(ADMISSION_PATH.read_text(encoding="utf-8")))
    extracted = extract_approved_source(
        admission=admission,
        payload=json.loads(SNAPSHOTS_PATH.read_text(encoding="utf-8")),
    )
    with pytest.raises(SemanticDatasetError, match="frozen source lineage"):
        build_semantic_dataset(
            source_dataset=source_dataset,
            extracted_source=extracted,
            annotations=annotations,
        )
    assert dataset.source_manifest_sha256 != "0" * 64


def test_frozen_embedding_and_offline_model_boundaries_reject_tampering(tmp_path) -> None:
    dataset = build_semantic_fixture()
    artifact = _fake_embeddings()
    assert len(validate_frozen_embeddings(artifact, dataset=dataset)) == 16

    tampered = copy.deepcopy(artifact)
    tampered["root_sha256"] = "0" * 64
    with pytest.raises(SemanticModelError, match="checksum"):
        validate_frozen_embeddings(tampered, dataset=dataset)

    with pytest.raises(SemanticModelUnavailableError, match="unavailable"):
        OfflineSemanticEncoder(cache_path=tmp_path / "missing")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "model.safetensors").write_bytes(b"not-approved")
    with pytest.raises(SemanticModelUnavailableError, match="checksum"):
        OfflineSemanticEncoder(cache_path=cache)


def test_pytorch_head_is_reproducible_checksum_bound_and_not_promoted() -> None:
    dataset = build_semantic_fixture()
    embeddings = _fake_embeddings()
    first_model, first_evaluation = train_semantic_experiment(
        dataset,
        embeddings,
        training_code_commit="f" * 40,
        risk_comparison=_risk_comparison(),
    )
    second_model, second_evaluation = train_semantic_experiment(
        dataset,
        embeddings,
        training_code_commit="f" * 40,
        risk_comparison=_risk_comparison(),
    )

    assert first_model == second_model
    assert first_evaluation == second_evaluation
    validate_semantic_model_artifact(first_model)
    assert first_model["lifecycle"] == "candidate_not_promoted"
    assert first_model["probability_display_allowed"] is False
    assert first_evaluation["promotion"] == {
        "active_model_changed": False,
        "decision": "candidate_not_promoted",
        "human_approval_required": True,
        "rollback": "deterministic-heuristic-v1",
    }
    incremental = first_evaluation["incremental_value"]
    assert isinstance(incremental, dict)
    assert incremental["decision"] == "keep_semantic_optional_not_integrated"
    assert incremental["active_recommendation_changed"] is False
    assert not all(incremental["gate_checks"].values())

    rows = validate_frozen_embeddings(embeddings, dataset=dataset)
    vector = tuple(rows["m4-011"]["original"]["vector"])
    scored = score_semantic_embedding(first_model, embedding=vector)
    assert scored.artifact_sha256 == first_model["artifact_sha256"]
    assert scored.calibrated_probability is None
    assert scored.probability_display_allowed is False

    tampered = copy.deepcopy(first_model)
    tampered["state"]["bias"][0] = 999.0
    with pytest.raises(SemanticModelError, match="checksum"):
        validate_semantic_model_artifact(tampered)
