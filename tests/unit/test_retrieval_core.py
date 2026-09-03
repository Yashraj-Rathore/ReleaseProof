from __future__ import annotations

import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from adapters.retrieval import (
    DeterministicEmbeddingProvider,
    DeterministicReranker,
    LocalModelUnavailableError,
    SentenceTransformerEmbeddingProvider,
)
from packages.retrieval_core import (
    EMBEDDING_ARTIFACT,
    RERANKER_ARTIFACT,
    ChunkCandidate,
    EvaluationCase,
    EvidenceDocumentInput,
    EvidenceSourceType,
    chunk_document,
    evaluate_rankings,
    normalize_fts_text,
    reciprocal_rank_fusion,
    rerank_candidates,
)

ROOT = Path(__file__).resolve().parents[2]


def _document(*, source_id: str, content: str, approved: bool = True) -> EvidenceDocumentInput:
    return EvidenceDocumentInput(
        source_type=(
            EvidenceSourceType.PYTHON_SOURCE
            if source_id.endswith(".py")
            else EvidenceSourceType.DOCUMENTATION
        ),
        source_id=source_id,
        source_version="sha256:fixture-v1",
        title="Fixture evidence",
        content=content,
        source_uri=f"fixture://{source_id}",
        approved=approved,
    )


def test_approved_documents_are_heading_and_python_ast_aware() -> None:
    markdown = chunk_document(
        _document(
            source_id="docs/runbook.md",
            content="# Authentication\nRotate credentials safely.\n\n## Rollback\nDisable the key.",
        )
    )
    python = chunk_document(
        _document(
            source_id="src/auth.py",
            content=(
                '"""Auth module."""\n\n'
                "def verify_signature(value: str) -> bool:\n"
                "    return bool(value)\n"
            ),
        )
    )

    assert [chunk.heading for chunk in markdown] == ["Authentication", "Rollback"]
    assert python[-1].heading == "function verify_signature"
    assert python[-1].start_line == 3
    assert all(chunk.content_sha256 and chunk.normalized_text for chunk in (*markdown, *python))


def test_unapproved_or_oversized_evidence_fails_closed() -> None:
    with pytest.raises(ValueError, match="explicitly approved"):
        _document(source_id="docs/unapproved.md", content="unsafe", approved=False)
    with pytest.raises(ValueError, match="byte limit"):
        _document(source_id="docs/large.md", content="x" * 262_145)


def test_code_aware_normalizer_preserves_identifiers_and_path_parts() -> None:
    normalized = normalize_fts_text("src/auth/verifyWebhookSignature.py rotate_apiToken")

    assert "src/auth/verifysignature.py" not in normalized
    assert "verifywebhooksignature" in normalized
    assert "verify" in normalized
    assert "webhook" in normalized
    assert "signature" in normalized
    assert "rotate_apitoken" in normalized
    assert "api" in normalized
    assert "token" in normalized


def test_rrf_exposes_component_ranks_and_bounded_reranker_scores() -> None:
    lexical = (
        ChunkCandidate("a", "auth webhook signature", "fixture:a", lexical_score=0.9),
        ChunkCandidate("b", "database migration", "fixture:b", lexical_score=0.8),
    )
    semantic = (
        ChunkCandidate("b", "database migration", "fixture:b", semantic_score=0.95),
        ChunkCandidate("c", "credential rotation", "fixture:c", semantic_score=0.7),
    )

    fused = reciprocal_rank_fusion(lexical, semantic, limit=3)
    reranked = rerank_candidates(
        query="webhook signature",
        candidates=fused,
        provider=DeterministicReranker(),
        limit=3,
    )

    assert fused[0].chunk_id == "b"
    assert fused[0].lexical_rank == 2
    assert fused[0].semantic_rank == 1
    assert fused[0].fusion_score is not None
    assert reranked[0].chunk_id == "a"
    assert reranked[0].reranker_score is not None


def test_retrieval_metrics_include_recall_mrr_and_graded_ndcg() -> None:
    cases = (
        EvaluationCase(query_id="q1", relevance={"a": 3, "b": 1}),
        EvaluationCase(query_id="q2", relevance={"c": 2}),
    )
    result = evaluate_rankings(
        cases=cases,
        rankings={"q1": ("b", "a", "z"), "q2": ("z", "c", "a")},
        k=2,
    )

    assert result["recall_at_k"] == 1.0
    assert result["mrr_at_k"] == 0.75
    assert 0.0 < float(result["ndcg_at_k"]) < 1.0


def test_fake_embedding_is_repeatable_and_versioned_without_a_model_download() -> None:
    provider = DeterministicEmbeddingProvider()
    first = provider.embed(("webhook signature verification",))
    second = provider.embed(("webhook signature verification",))

    assert first == second
    assert len(first[0]) == 384
    assert provider.artifact.license == "synthetic-test-fixture"
    assert provider.artifact.model_id.startswith("releaseproof-fixture/")


def test_exact_real_artifacts_are_pinned_and_require_a_verified_local_cache(
    tmp_path: Path,
) -> None:
    assert EMBEDDING_ARTIFACT.revision == "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    assert EMBEDDING_ARTIFACT.dimension == 384
    assert RERANKER_ARTIFACT.revision == "4bebbd56fc380a66525f95b03d4ec1a4b41a4f1e"
    with pytest.raises(LocalModelUnavailableError, match="cache is unavailable"):
        SentenceTransformerEmbeddingProvider(cache_path=tmp_path / "missing")

    cache = tmp_path / "model"
    cache.mkdir()
    (cache / "model.safetensors").write_bytes(b"not-the-approved-artifact")
    with pytest.raises(LocalModelUnavailableError, match="checksum mismatch"):
        SentenceTransformerEmbeddingProvider(cache_path=cache)


def test_model_artifact_revision_and_checksum_are_not_mutable_aliases() -> None:
    with pytest.raises(ValueError, match="exact lowercase Git commit"):
        replace(EMBEDDING_ARTIFACT, revision="main")
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        replace(RERANKER_ARTIFACT, safetensors_sha256="not-a-checksum")


def test_m6_m11_runtime_and_optional_semantic_dependencies_are_exact() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "pgvector==0.5.0" in project["project"]["dependencies"]
    assert project["dependency-groups"]["semantic"] == [
        "sentence-transformers==6.0.0",
        "torch==2.13.0",
        "transformers==5.15.1",
    ]
    assert project["tool"]["uv"]["sources"]["torch"] == {"index": "pytorch-cpu"}
    assert project["tool"]["uv"]["index"] == [
        {
            "explicit": True,
            "name": "pytorch-cpu",
            "url": "https://download.pytorch.org/whl/cpu",
        }
    ]
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    assert 'name = "pgvector"\nversion = "0.5.0"' in lock
    assert 'name = "sentence-transformers"\nversion = "6.0.0"' in lock
    assert 'name = "torch"\nversion = "2.13.0+cpu"' in lock
    assert 'name = "transformers"\nversion = "5.15.1"' in lock
