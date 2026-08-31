"""Frozen-ranking retrieval metrics without ML framework dependencies."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    query_id: str
    relevance: dict[str, int]

    def __post_init__(self) -> None:
        if not self.query_id or not self.relevance:
            raise ValueError("evaluation cases require an ID and relevance judgments")
        if any(grade < 0 or grade > 3 for grade in self.relevance.values()):
            raise ValueError("relevance grades must be between zero and three")


def _recall_at_k(case: EvaluationCase, ranking: tuple[str, ...], k: int) -> float:
    relevant = {item for item, grade in case.relevance.items() if grade > 0}
    return len(relevant.intersection(ranking[:k])) / len(relevant)


def _reciprocal_rank(case: EvaluationCase, ranking: tuple[str, ...], k: int) -> float:
    for rank, item in enumerate(ranking[:k], start=1):
        if case.relevance.get(item, 0) > 0:
            return 1.0 / rank
    return 0.0


def _dcg(case: EvaluationCase, ranking: tuple[str, ...], k: int) -> float:
    return sum(
        (2.0 ** case.relevance.get(item, 0) - 1.0) / math.log2(rank + 1)
        for rank, item in enumerate(ranking[:k], start=1)
    )


def _ndcg_at_k(case: EvaluationCase, ranking: tuple[str, ...], k: int) -> float:
    ideal = tuple(
        item
        for item, _grade in sorted(case.relevance.items(), key=lambda pair: (-pair[1], pair[0]))
    )
    ideal_dcg = _dcg(case, ideal, k)
    return 0.0 if ideal_dcg == 0.0 else _dcg(case, ranking, k) / ideal_dcg


def evaluate_rankings(
    *,
    cases: tuple[EvaluationCase, ...],
    rankings: dict[str, tuple[str, ...]],
    k: int,
) -> dict[str, object]:
    if not cases or k < 1:
        raise ValueError("evaluation requires cases and a positive K")
    missing = [case.query_id for case in cases if case.query_id not in rankings]
    if missing:
        raise ValueError(f"rankings missing evaluation cases: {', '.join(missing)}")
    per_query: list[dict[str, object]] = []
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    for case in cases:
        ranking = rankings[case.query_id]
        recall = round(_recall_at_k(case, ranking, k), 12)
        reciprocal_rank = round(_reciprocal_rank(case, ranking, k), 12)
        ndcg = round(_ndcg_at_k(case, ranking, k), 12)
        recalls.append(recall)
        reciprocal_ranks.append(reciprocal_rank)
        ndcgs.append(ndcg)
        per_query.append(
            {
                "query_id": case.query_id,
                "recall_at_k": recall,
                "reciprocal_rank": reciprocal_rank,
                "ndcg_at_k": ndcg,
                "ranking": list(ranking[:k]),
            }
        )
    count = len(per_query)
    return {
        "k": k,
        "query_count": count,
        "recall_at_k": round(sum(recalls) / count, 12),
        "mrr_at_k": round(sum(reciprocal_ranks) / count, 12),
        "ndcg_at_k": round(sum(ndcgs) / count, 12),
        "per_query": per_query,
    }
