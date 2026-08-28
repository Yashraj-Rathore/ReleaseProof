"""Deterministic orchestration across normalization, graph, history, features and evidence."""

from __future__ import annotations

from datetime import datetime

from packages.change_intel.contracts import (
    ChangeIntelligenceResult,
    HistoricalChange,
    RawChangedFile,
    SourceTree,
    canonical_hash,
)
from packages.change_intel.diffs import normalize_diff
from packages.change_intel.features import extract_feature_set, render_risk_factors
from packages.change_intel.graph import (
    build_python_import_graph,
    compute_blast_radius,
    unavailable_graph,
)
from packages.change_intel.history import compute_historical_statistics


def analyze_change(
    *,
    changed_files: tuple[RawChangedFile, ...],
    prediction_time: datetime,
    history: tuple[HistoricalChange, ...],
    source_tree: SourceTree | None,
    current_author_key: str | None,
    commit_count: int | None,
    history_truncated: bool = False,
) -> ChangeIntelligenceResult:
    normalized_diff = normalize_diff(changed_files)
    graph = (
        build_python_import_graph(source_tree)
        if source_tree is not None
        else unavailable_graph("source_tree_unavailable")
    )
    blast_radius = compute_blast_radius(normalized_diff, graph)
    statistics = compute_historical_statistics(
        normalized_diff,
        history,
        prediction_time=prediction_time,
        current_author_key=current_author_key,
        history_truncated=history_truncated,
    )
    features = extract_feature_set(
        normalized_diff,
        blast_radius,
        statistics,
        commit_count=commit_count,
    )
    risk_factors = render_risk_factors(normalized_diff, blast_radius, features)
    payload = {
        "blast_radius": blast_radius.as_dict(),
        "features": features.as_dict(),
        "graph": graph.as_dict(),
        "history": statistics.as_dict(),
        "normalized_diff": normalized_diff.as_dict(),
        "risk_factors": [factor.as_dict() for factor in risk_factors],
    }
    return ChangeIntelligenceResult(
        normalized_diff=normalized_diff,
        graph=graph,
        blast_radius=blast_radius,
        history=statistics,
        features=features,
        risk_factors=risk_factors,
        result_hash=canonical_hash(payload),
    )
