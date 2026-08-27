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
