# 06 — Change Intelligence and Blast Radius

## Goal
Create deterministic explainable facts before ML/LLM. These facts become features, retrieval filters and evidence.

## Inputs
Exact base/head SHAs, normalized file patches, selected inert source/tree data, repository language/framework policy, optional prior graph.

## Feature schema v1
Examples:
- lines added/deleted, files changed, language/file-type distribution
- tests changed
- migration/schema change
- dependency manifest/lockfile change
- auth/security-sensitive path flags
- deployment/CI/config changes
- API surface heuristic
- rename/delete/binary/generated/vendored handling
- recent file churn
- touched-area proxy-failure history
- change concentration/entropy
- commit count
- blast-radius counts/depth
Unknown != zero. Names/semantics are versioned.

## Python graph v1
Static `ast` import/module graph plus generic directory heuristics. A later assigned language-adapter issue may add Tree-sitter only with licensed fixtures and a measured coverage/correctness benefit over the existing parser. Never import/execute customer modules to discover dependencies.

Blast radius:
- changed nodes
- reverse dependents to bounded depth
- edge-type/distance weights
- configured critical-path tags
- impacted tests where mappings exist

Do not claim a dynamic call graph.

## Evidence
Every deterministic flag includes rule ID, value, reason, bounded source references and producer version.

## Reproducibility
Same snapshot + extractor + policy => same feature/graph hash. Golden fixture tests enforce it.

## Implemented v1 contracts

- Diff `change-diff-v1`: at most 1,000 unique repository-relative paths, 64 KiB UTF-8 per patch and
  1 MiB combined patch text. Paths/newlines/order are normalized; truncation and missing patches are
  explicit. Classification covers common source/config/dependency/test/migration/docs/binary,
  generated and vendored facts plus bounded sensitive-area tags.
- Feature `change-features-v1`: exact names, scalar types, nullable/default semantics and per-feature
  provenance are source controlled. Unknown history/graph/commit inputs are null with a reason, not
  measured zero. Author identity, labels and post-outcome facts are excluded.
- Graph `python-import-graph-v1`: parses at most 5,000 inert files, 256 KiB per file, 5 MiB total and
  25,000 internal edges. It never imports source. External, dynamic, parse-error, oversized and
  unsupported-language findings are explicit. This is a static import graph, not a call graph.
- Blast radius walks reverse imports to depth 5 and at most 1,000 affected nodes, preserving one
  deterministic evidence path per node. Partial/missing/truncated changed-path coverage makes blast
  features null rather than undercounted.
- History `repository-history-v1` includes at most 10,000 repository snapshots in the 90-day window
  whose recorded observation time is strictly earlier than prediction time. It reports file/module
  touches, line churn, check-failure proxies, aggregate opaque-author familiarity, coverage and
  truncation. A failure proxy is not called an incident.
- Evidence `deterministic-risk-factor-v1` renders every feature, normalized file fact, graph path and
  missing-data state with a rule ID, reason, bounded source references and producer version. It has
  no composite score, threshold policy, band or recommendation.
