"""Build or verify the frozen synthetic M6 retrieval evaluation artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any, cast

from adapters.retrieval import DeterministicEmbeddingProvider, DeterministicReranker
from packages.retrieval_core import (
    EMBEDDING_ARTIFACT,
    FTS_CONFIGURATION,
    FTS_PROFILE_VERSION,
    FUSION_VERSION,
    NORMALIZER_VERSION,
    RERANKER_ARTIFACT,
    RETRIEVAL_EVALUATION_VERSION,
    ChunkCandidate,
    EvaluationCase,
    cosine_similarity,
    evaluate_rankings,
    lexical_score,
    reciprocal_rank_fusion,
    rerank_candidates,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "retrieval" / "m6_relevance_v1.json"
ARTIFACT_PATH = ROOT / "artifacts" / "evaluation" / "m6_retrieval_eval_v1.json"
QUALITY_K = 3
LATENCY_REPETITIONS = 100


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _load_fixture() -> dict[str, Any]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != "m6-relevance-fixture-v1"
        or payload.get("synthetic") is not True
    ):
        raise ValueError("M6 relevance fixture identity is invalid")
    corpus = payload.get("corpus")
    queries = payload.get("queries")
    if not isinstance(corpus, list) or not isinstance(queries, list) or not corpus or not queries:
        raise ValueError("M6 relevance fixture must contain corpus and queries")
    return cast(dict[str, Any], payload)


def _rankings(fixture: dict[str, Any]) -> dict[str, dict[str, tuple[str, ...]]]:
    corpus = fixture["corpus"]
    queries = fixture["queries"]
    embedding_provider = DeterministicEmbeddingProvider()
    reranker = DeterministicReranker()
    texts = tuple(str(item["text"]) for item in corpus)
    document_vectors = embedding_provider.embed(texts)
    variants: dict[str, dict[str, tuple[str, ...]]] = {
        "lexical": {},
        "vector": {},
        "hybrid_rrf": {},
        "reranked": {},
    }
    for query_item in queries:
        query_id = str(query_item["query_id"])
        query = str(query_item["query"])
        query_vector = embedding_provider.embed((query,))[0]
        lexical_scored = sorted(
            (
                (lexical_score(query, str(item["text"])), str(item["chunk_id"]), index)
                for index, item in enumerate(corpus)
            ),
            key=lambda row: (-row[0], row[1]),
        )
        vector_scored = sorted(
            (
                (
                    cosine_similarity(query_vector, document_vectors[index]),
                    str(item["chunk_id"]),
                    index,
                )
                for index, item in enumerate(corpus)
            ),
            key=lambda row: (-row[0], row[1]),
        )
        lexical_candidates = tuple(
            ChunkCandidate(
                chunk_id=chunk_id,
                content=str(corpus[index]["text"]),
                source_ref=str(corpus[index]["source_ref"]),
                lexical_score=score,
            )
            for score, chunk_id, index in lexical_scored
        )
        vector_candidates = tuple(
            ChunkCandidate(
                chunk_id=chunk_id,
                content=str(corpus[index]["text"]),
                source_ref=str(corpus[index]["source_ref"]),
                semantic_score=score,
            )
            for score, chunk_id, index in vector_scored
        )
        fused = reciprocal_rank_fusion(
            lexical_candidates,
            vector_candidates,
            limit=len(corpus),
        )
        reranked = rerank_candidates(
            query=query,
            candidates=fused,
            provider=reranker,
            limit=len(corpus),
        )
        variants["lexical"][query_id] = tuple(item[1] for item in lexical_scored)
        variants["vector"][query_id] = tuple(item[1] for item in vector_scored)
        variants["hybrid_rrf"][query_id] = tuple(item.chunk_id for item in fused)
        variants["reranked"][query_id] = tuple(item.chunk_id for item in reranked)
    return variants


def _quality(fixture: dict[str, Any]) -> dict[str, object]:
    cases = tuple(
        EvaluationCase(
            query_id=str(item["query_id"]),
            relevance={str(key): int(value) for key, value in item["relevance"].items()},
        )
        for item in fixture["queries"]
    )
    return {
        variant: evaluate_rankings(cases=cases, rankings=rankings, k=QUALITY_K)
        for variant, rankings in _rankings(fixture).items()
    }


def _latency(fixture: dict[str, Any]) -> dict[str, object]:
    samples: list[float] = []
    for _index in range(LATENCY_REPETITIONS):
        start = time.perf_counter_ns()
        _rankings(fixture)
        samples.append((time.perf_counter_ns() - start) / 1_000_000.0)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, int(0.95 * len(ordered)))
    return {
        "measurement": "single-process in-memory full five-query ablation suite",
        "repetitions": LATENCY_REPETITIONS,
        "median_ms": round(statistics.median(samples), 6),
        "p95_ms": round(ordered[p95_index], 6),
        "minimum_ms": round(min(samples), 6),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor() or "not reported",
        },
        "limitations": (
            "This excludes PostgreSQL network/query time and real transformer inference; "
            "it is a local deterministic harness measurement only."
        ),
    }


def _stable_artifact(fixture: dict[str, Any]) -> dict[str, object]:
    fixture_bytes = _canonical_json(fixture)
    corpus_bytes = sum(len(str(item["text"]).encode()) for item in fixture["corpus"])
    return {
        "schema_version": RETRIEVAL_EVALUATION_VERSION,
        "synthetic": True,
        "fixture": {
            "path": FIXTURE_PATH.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(fixture_bytes).hexdigest(),
            "query_count": len(fixture["queries"]),
            "chunk_count": len(fixture["corpus"]),
            "corpus_text_bytes": corpus_bytes,
            "license": fixture["license"],
            "usage": fixture["usage"],
        },
        "configuration": {
            "fts_configuration": FTS_CONFIGURATION,
            "fts_profile_version": FTS_PROFILE_VERSION,
            "normalizer_version": NORMALIZER_VERSION,
            "fusion_version": FUSION_VERSION,
            "quality_k": QUALITY_K,
            "evaluation_embedding": {
                "version": DeterministicEmbeddingProvider().artifact.version,
                "synthetic_fake": True,
                "dimension": 384,
            },
            "selected_real_embedding": {
                "model_id": EMBEDDING_ARTIFACT.model_id,
                "revision": EMBEDDING_ARTIFACT.revision,
                "safetensors_sha256": EMBEDDING_ARTIFACT.safetensors_sha256,
                "dimension": EMBEDDING_ARTIFACT.dimension,
                "license": EMBEDDING_ARTIFACT.license,
            },
            "selected_real_reranker": {
                "model_id": RERANKER_ARTIFACT.model_id,
                "revision": RERANKER_ARTIFACT.revision,
                "safetensors_sha256": RERANKER_ARTIFACT.safetensors_sha256,
                "license": RERANKER_ARTIFACT.license,
            },
        },
        "quality": _quality(fixture),
        "failure_modes": [
            "No active lexical profile returns explicit unavailable status.",
            "No active or compatible embedding profile degrades to lexical evidence.",
            "Embedding provider outage does not erase lexical evidence.",
            "Reranker outage preserves deterministic hybrid ordering.",
            "Expired documents and cross-tenant/repository rows are excluded before ranking.",
        ],
        "index_size_evidence": {
            "status": "not yet measured on a representative PostgreSQL corpus",
            "fixture_corpus_text_bytes": corpus_bytes,
            "fixture_fake_vector_float_count": len(fixture["corpus"]) * 384,
        },
        "decision": {
            "real_reranker_active_by_default": False,
            "reason": (
                "Only a synthetic fake-provider harness is evaluated in M6. The exact real "
                "reranker remains opt-in until an allowed representative corpus and local "
                "artifact benchmark demonstrate incremental value."
            ),
            "fallback": "hybrid RRF, or lexical-only when semantic retrieval is unavailable",
        },
        "limitations": [
            "All relevance labels and content are explicitly synthetic.",
            "The fixture is small, English-only, and designed to validate the evaluation harness.",
            "No customer/public-repository retrieval quality is measured.",
            "The pinned real embedding and reranker weights were not downloaded or executed.",
            (
                "PostgreSQL on-disk index size and representative end-to-end latency are not "
                "yet measured."
            ),
        ],
    }


def _with_hash_and_latency(
    stable: dict[str, object], latency: dict[str, object]
) -> dict[str, object]:
    artifact = {**stable, "latency_evidence": latency}
    root_hash = hashlib.sha256(_canonical_json(artifact)).hexdigest()
    return {**artifact, "root_sha256": root_hash}


def _verify() -> None:
    fixture = _load_fixture()
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    root_hash = committed.pop("root_sha256", None)
    if root_hash != hashlib.sha256(_canonical_json(committed)).hexdigest():
        raise ValueError("committed M6 evaluation artifact checksum is invalid")
    expected_stable = _stable_artifact(fixture)
    committed_stable = {key: value for key, value in committed.items() if key != "latency_evidence"}
    if committed_stable != expected_stable:
        raise ValueError("committed M6 evaluation quality/configuration is stale")
    current_latency = _latency(fixture)
    print(json.dumps({"status": "verified", "current_latency": current_latency}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("choose exactly one of --write or --check")
    if args.write:
        fixture = _load_fixture()
        artifact = _with_hash_and_latency(_stable_artifact(fixture), _latency(fixture))
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_bytes(_canonical_json(artifact))
        print(f"wrote {ARTIFACT_PATH.relative_to(ROOT)}")
    else:
        _verify()
    return 0


if __name__ == "__main__":
    sys.exit(main())
