# 17 — MLOps and Model Governance

## MLflow
Use for experiment parameters/metrics/artifacts, model lifecycle, prompt/trace/evaluation capabilities supported by the pinned version, and comparison dashboards.

## Lineage
Every promoted model links:
`code commit -> dataset manifest -> feature version -> training config -> evaluation -> artifact checksum -> promotion decision`.

## Lifecycle
Candidate -> approved -> retired. No mutable “latest” in inference. Promotion/rollback is explicit/human-controlled.

## Versioned AI configuration
Prompts, embedding model, chunking, fusion, reranker, agent graph and recommendation policy all have versions and evaluation gates.

## Feedback
Deployment outcomes enter org-local learning only if opt-in, observation window complete, label provenance known, and training policy allows it. Unknown/ambiguous stays unknown.

## Drift/data quality
Monitor only when sample size supports interpretation. Organization-local learned models require minimum data; otherwise use global/public baseline + local deterministic/RAG history.

## Reproducibility
Seeds where possible, lock/environment/hardware metadata, immutable splits, raw evaluation outputs, package code shared by notebooks and production.

M4's first governed lineage is source admission/hash -> extraction code commit -> immutable snapshot
hash -> `change-features-v1` row/hash -> frozen split/hash -> `deterministic-heuristic-v1` artifact
and threshold policy -> raw evaluation/hash. It is committed as a synthetic fixture artifact; M13
will register later formal experiments in MLflow without replacing this source lineage.

M5 extends that chain with training-code commit -> exact pinned CPU runtime -> train-only
preprocessor/hash -> validation-selected logistic/XGBoost configurations and threshold policy ->
one held-out raw evaluation -> model/root checksums -> explicit `candidate_not_promoted` decision ->
deterministic rollback artifact. No mutable `latest` identifier or automatic promotion is used.
M13 will import/register this lineage in MLflow rather than changing the historical evidence.

M6 adds source/version/hash/retention -> chunk/normalizer version -> lexical profile or exact
embedding artifact/revision/checksum/dimension -> physical index -> fusion/reranker version ->
frozen relevance fixture/hash -> raw rankings/metrics/latency limitations -> activation decision.
Profiles build beside active rows and switch transactionally only after completeness and scope
checks. The real reranker is not active because only a deterministic synthetic fake was evaluated;
M13 can register this evidence without changing that historical decision.
