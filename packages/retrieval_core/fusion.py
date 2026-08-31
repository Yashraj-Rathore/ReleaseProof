"""Deterministic reciprocal-rank fusion and bounded optional reranking."""

from __future__ import annotations

from dataclasses import replace

from packages.retrieval_core.contracts import MAX_CANDIDATES, ChunkCandidate, RerankerProvider

RRF_K = 60


def reciprocal_rank_fusion(
    lexical: tuple[ChunkCandidate, ...],
    semantic: tuple[ChunkCandidate, ...],
    *,
    limit: int,
) -> tuple[ChunkCandidate, ...]:
    if not 1 <= limit <= MAX_CANDIDATES:
        raise ValueError("fusion limit is outside the bounded contract")
    combined: dict[str, ChunkCandidate] = {}
    scores: dict[str, float] = {}
    for rank, candidate in enumerate(lexical, start=1):
        combined[candidate.chunk_id] = replace(candidate, lexical_rank=rank)
        scores[candidate.chunk_id] = scores.get(candidate.chunk_id, 0.0) + 1.0 / (RRF_K + rank)
    for rank, candidate in enumerate(semantic, start=1):
        current = combined.get(candidate.chunk_id)
        if current is None:
            combined[candidate.chunk_id] = replace(candidate, semantic_rank=rank)
        else:
            combined[candidate.chunk_id] = replace(
                current,
                semantic_score=candidate.semantic_score,
                semantic_rank=rank,
            )
        scores[candidate.chunk_id] = scores.get(candidate.chunk_id, 0.0) + 1.0 / (RRF_K + rank)
    ranked = [
        replace(candidate, fusion_score=scores[chunk_id])
        for chunk_id, candidate in combined.items()
    ]
    ranked.sort(key=lambda item: (-(item.fusion_score or 0.0), item.chunk_id))
    return tuple(ranked[:limit])


def rerank_candidates(
    *,
    query: str,
    candidates: tuple[ChunkCandidate, ...],
    provider: RerankerProvider,
    limit: int,
) -> tuple[ChunkCandidate, ...]:
    if not 1 <= limit <= MAX_CANDIDATES or len(candidates) > MAX_CANDIDATES:
        raise ValueError("reranker candidate bounds were exceeded")
    scores = provider.score(query, tuple(candidate.content for candidate in candidates))
    if len(scores) != len(candidates) or any(not isinstance(score, float) for score in scores):
        raise ValueError("reranker returned an invalid score contract")
    ranked = [
        replace(candidate, reranker_score=score)
        for candidate, score in zip(candidates, scores, strict=True)
    ]
    ranked.sort(
        key=lambda item: (-(item.reranker_score or 0.0), -(item.fusion_score or 0.0), item.chunk_id)
    )
    return tuple(ranked[:limit])
