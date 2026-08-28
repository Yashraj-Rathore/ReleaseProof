"""Framework-light deterministic change-intelligence contracts and algorithms."""

from packages.change_intel.contracts import (
    DIFF_SCHEMA_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    EXTRACTOR_VERSION,
    FEATURE_SCHEMA_VERSION,
    GRAPH_SCHEMA_VERSION,
    HISTORY_SCHEMA_VERSION,
    BlastRadius,
    ChangeIntelligenceResult,
    FeatureSet,
    HistoricalChange,
    HistoricalFileChange,
    HistoricalStatistics,
    ImportGraph,
    NormalizedDiff,
    RawChangedFile,
    RiskFactor,
    SourceFile,
    SourceTree,
    SourceTreeProvider,
    SourceTreeProviderError,
    canonical_hash,
)
from packages.change_intel.diffs import normalize_diff
from packages.change_intel.features import (
    FEATURE_DEFINITIONS,
    extract_feature_set,
    render_risk_factors,
)
from packages.change_intel.graph import build_python_import_graph, compute_blast_radius
from packages.change_intel.history import compute_historical_statistics
from packages.change_intel.pipeline import analyze_change

__all__ = [
    "DIFF_SCHEMA_VERSION",
    "EVIDENCE_SCHEMA_VERSION",
    "EXTRACTOR_VERSION",
    "FEATURE_DEFINITIONS",
    "FEATURE_SCHEMA_VERSION",
    "GRAPH_SCHEMA_VERSION",
    "HISTORY_SCHEMA_VERSION",
    "BlastRadius",
    "ChangeIntelligenceResult",
    "FeatureSet",
    "HistoricalChange",
    "HistoricalFileChange",
    "HistoricalStatistics",
    "ImportGraph",
    "NormalizedDiff",
    "RawChangedFile",
    "RiskFactor",
    "SourceFile",
    "SourceTree",
    "SourceTreeProvider",
    "SourceTreeProviderError",
    "analyze_change",
    "build_python_import_graph",
    "canonical_hash",
    "compute_blast_radius",
    "compute_historical_statistics",
    "extract_feature_set",
    "normalize_diff",
    "render_risk_factors",
]
