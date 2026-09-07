# 17 — MLOps and Model Governance

## MLflow
Use for experiment parameters/metrics/artifacts, model lifecycle, prompt/trace/evaluation capabilities supported by the pinned version, and comparison dashboards.

## Lineage
Every promoted model links:
`code commit -> dataset manifest -> feature version -> training config -> evaluation -> artifact checksum -> promotion decision`.

## Lifecycle
Candidate -> staging -> active -> retired. Approval is immutable transition evidence rather than a
lifecycle state. No mutable “latest” in inference. Promotion/rollback is explicit/human-controlled.

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

M7 adds immutable privacy policy ID/version/hash -> prompt/schema semantic versions and content
hashes -> provider/model/adapter/SDK identity -> cited source evidence IDs -> strict structured
suggestion -> usage/cost/latency -> frozen fixture/evaluation root hash. Hosted pricing and provider
terms are external reviewed inputs rather than mutable constants. The deterministic fake remains
the default because the frozen synthetic suite does not measure hosted-model quality; later MLflow
registration must preserve that decision and the original raw artifact.

M8 adds completed M7 evidence identity -> strict generated-test schema/adapter versions -> cited
source IDs -> immutable proposal content hash/revision -> static-validator version/result ->
append-only human lifecycle/audit events -> bounded export. The frozen synthetic fixture and raw
evaluation checksum are preserved beside that chain. Acceptance is not model promotion or
execution authorization; future M9 evidence must name the exact exported proposal and a separate
execution-plan hash without rewriting M8 history.

M9/M10 extend that chain with exact execution plan + separate human approval + signed bounded run
result + differential plan + controlled base/candidate revisions + workload/mask/mutation versions
+ signed result + immutable `recommendation-fusion-v1` input/decision hashes. A later recommendation
policy must create a new decision version; it cannot rewrite historical M10 decisions. The fixture
evaluation and live CI evidence remain distinct, and neither promotes arbitrary repository
execution.

M11 adds exact M4 source/admission/split/leakage hashes -> outcome-blind semantic annotation and
text versions -> pinned encoder revision/license/safetensors checksum -> frozen embedding checksum
-> training-code commit and deterministic PyTorch config/checkpoints -> held-out raw predictions,
errors, robustness, latency and calibration abstention -> model-state/artifact checksums ->
incremental-value gates -> `candidate_not_promoted`. The normal reproduction path uses committed
embeddings without network access; explicit weight provisioning is separate. M13 may register this
lineage but cannot convert the historical non-promotion into approval or a mutable `latest` alias.

## M13 implementation

`formal-experiment-v1` and `evaluation-registry-entry-v1` make complete lineage mandatory and
checksum the canonical record. MLflow 3.15.2 runs in a separate pinned local container with
PostgreSQL metadata and proxied SeaweedFS artifacts. The application uses
`mlflow-skinny==3.15.2`; full MLflow cannot share M5's pandas 3.0.5 environment because the full
package requires pandas below 3. Exact client/server versions are checked before registration.

M4/M5/M11 formal histories and M6/M7/M12 evaluation histories are imported as safe synthetic
metadata without rewriting their source artifacts or promotion decisions. The deterministic
heuristic stays active. `GovernedModelArtifact` and append-only transition events bind every
candidate/staging/active/retired/rollback action to evaluation, compatibility and reviewer
evidence; an atomic deployment pointer preserves a known rollback.

Delayed 30–365 day outcomes remain separate from immutable predictions and are never shared-
training eligible. Aggregate drift checks cover exact schema, missingness, PSI distribution shift
and labeled performance drop with sample-size gates. Non-pass decisions require human review and
cannot automatically retrain or promote. Exact evidence and limitations are in docs/49.
