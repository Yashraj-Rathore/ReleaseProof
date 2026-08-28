from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from packages.change_intel import (
    FEATURE_DEFINITIONS,
    HistoricalChange,
    HistoricalFileChange,
    RawChangedFile,
    analyze_change,
    build_python_import_graph,
    compute_blast_radius,
    compute_historical_statistics,
    normalize_diff,
)
from tests.change_intel_fixtures import fixture_source_tree

ROOT = Path(__file__).resolve().parents[2]


def _changed_files() -> tuple[RawChangedFile, ...]:
    return (
        RawChangedFile(
            path="src\\fixture_app\\pricing.py",
            additions=4,
            deletions=1,
            patch="@@ -1 +1 @@\n-old\n+new",
        ),
    )


def _history() -> tuple[HistoricalChange, ...]:
    return (
        HistoricalChange(
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            files=(HistoricalFileChange("src/fixture_app/pricing.py", 3, 2),),
            author_key="fixture-author",
            failed_check_proxy=True,
        ),
        HistoricalChange(
            observed_at=datetime(2026, 1, 8, tzinfo=UTC),
            files=(HistoricalFileChange("src/fixture_app/service.py", 2, 0),),
            author_key="other-author",
            failed_check_proxy=False,
        ),
        HistoricalChange(
            observed_at=datetime(2026, 1, 11, tzinfo=UTC),
            files=(HistoricalFileChange("src/fixture_app/pricing.py", 999, 999),),
            author_key="fixture-author",
            failed_check_proxy=True,
        ),
    )


def _result():  # type: ignore[no-untyped-def]
    return analyze_change(
        changed_files=_changed_files(),
        prediction_time=datetime(2026, 1, 10, tzinfo=UTC),
        history=_history(),
        source_tree=fixture_source_tree(),
        current_author_key="fixture-author",
        commit_count=2,
    )


def test_diff_normalization_is_stable_bounded_and_classified() -> None:
    normalized = normalize_diff(
        (
            RawChangedFile("tests\\test_api.py", 2, 1, patch="line1\r\nline2"),
            RawChangedFile(
                "src/new.py",
                1,
                0,
                status="renamed",
                previous_path="src/old.py",
            ),
            RawChangedFile("assets/logo.png", 0, 0, patch=None),
        )
    )

    assert [file.path for file in normalized.files] == [
        "assets/logo.png",
        "src/new.py",
        "tests/test_api.py",
    ]
    assert normalized.files[0].is_binary is True
    assert normalized.files[1].previous_path == "src/old.py"
    assert normalized.files[2].file_type == "test"
    assert normalized.files[2].patch == "line1\nline2"
    assert (
        normalize_diff(
            tuple(
                reversed(
                    (
                        RawChangedFile("tests/test_api.py", 2, 1, patch="line1\nline2"),
                        RawChangedFile(
                            "src/new.py", 1, 0, status="renamed", previous_path="src/old.py"
                        ),
                        RawChangedFile("assets/logo.png", 0, 0),
                    )
                )
            )
        ).diff_hash
        == normalized.diff_hash
    )
    with pytest.raises(ValueError, match="previous_path"):
        normalize_diff((RawChangedFile("src/new.py", 1, 0, status="renamed"),))


def test_graph_records_static_edges_and_explicit_unsupported_behavior() -> None:
    graph = build_python_import_graph(fixture_source_tree())
    normalized = normalize_diff(_changed_files())
    blast = compute_blast_radius(normalized, graph)

    assert graph.edges == (
        ("fixture_app.api", "fixture_app.service"),
        ("fixture_app.service", "fixture_app.pricing"),
        ("tests.pricing_check", "fixture_app.pricing"),
    )
    assert {finding.code for finding in graph.findings} >= {
        "dynamic_import_importlib",
        "external_import",
        "unsupported_language",
    }
    assert blast.direct_modules == ("fixture_app.service", "tests.pricing_check")
    assert blast.transitive_modules == ("fixture_app.api",)
    assert blast.impacted_tests == ("tests.pricing_check",)
    assert blast.max_depth == 2
    assert all(path.modules[0] == "fixture_app.pricing" for path in blast.evidence_paths)


def test_history_uses_only_facts_strictly_before_prediction_time() -> None:
    stats = compute_historical_statistics(
        normalize_diff(_changed_files()),
        _history(),
        prediction_time=datetime(2026, 1, 10, tzinfo=UTC),
        current_author_key="fixture-author",
    )

    assert stats.included_changes == 2
    assert stats.excluded_future_changes == 1
    assert stats.target_file_touches == 1
    assert stats.target_module_touches == 2
    assert stats.line_churn == 5
    assert stats.prior_failure_proxy_count == 1
    assert stats.ownership_familiarity == 0.5
    assert stats.missing == ()


def test_feature_schema_is_prediction_time_only_and_never_produces_a_score() -> None:
    result = _result()
    names = {definition.name for definition in FEATURE_DEFINITIONS}

    assert set(result.features.values) == names
    assert not any(token in name for name in names for token in ("label", "outcome", "author_id"))
    assert "score" not in result.features.values
    assert "recommendation" not in result.features.values
    assert all("score" not in factor.rule_id for factor in result.risk_factors)
    assert result.result_hash == _result().result_hash


def test_missing_history_and_partial_graph_are_null_not_measured_zero() -> None:
    result = analyze_change(
        changed_files=(RawChangedFile("frontend/app.js", 1, 0, patch="+change"),),
        prediction_time=datetime(2026, 1, 10, tzinfo=UTC),
        history=(),
        source_tree=fixture_source_tree(),
        current_author_key=None,
        commit_count=None,
    )

    assert result.features.values["historical_file_touches_90d"] is None
    assert result.features.values["blast_direct_modules"] is None
    assert "historical_file_touches_90d" in result.features.missing
    assert "blast_direct_modules" in result.features.missing


def test_fixture_graph_and_feature_behavior_matches_golden_contract() -> None:
    result = _result()
    golden = json.loads(
        (ROOT / "tests" / "golden" / "change_intel_v1.json").read_text(encoding="utf-8")
    )
    selected_features = {name: result.features.values[name] for name in golden["feature_values"]}
    actual = {
        "blast_radius": {
            "changed_modules": list(result.blast_radius.changed_modules),
            "direct_modules": list(result.blast_radius.direct_modules),
            "impacted_tests": list(result.blast_radius.impacted_tests),
            "max_depth": result.blast_radius.max_depth,
            "transitive_modules": list(result.blast_radius.transitive_modules),
        },
        "feature_values": selected_features,
        "graph_edges": [list(edge) for edge in result.graph.edges],
        "schema_versions": {
            "diff": result.normalized_diff.schema_version,
            "feature": result.features.schema_version,
            "graph": result.graph.schema_version,
            "history": result.history.schema_version,
        },
    }
    assert actual == golden
