# 16 — Testing, Quality and Evaluation

## Test pyramid
### Unit
Domain invariants, feature extraction, graph algorithms, schemas, thresholds, retrieval fusion, LLM validation, recommendation policy, execution-plan hashing.

### Integration
Real Postgres/pgvector, Redis, the pinned SeaweedFS S3 endpoint and controlled HTTP adapters/Testcontainers where useful. The object-store contract suite covers bucket readiness plus bounded put/head/get/delete, checksum, missing-object and unavailable-provider behavior; it must also pass against the deterministic fake.

### Contract
GitHub fixtures, provider schemas, model service, runner plan/results.

### Browser E2E
Playwright for demo/login/repository/PR evidence/policy/proposal/degradation flows.

## ML evaluation
Pinned manifest + split + feature version. CI uses smoke inference on pinned artifacts; expensive training/eval runs separately. Check train/serve consistency, leakage, prevalence, baseline comparison, threshold metrics, calibration and artifact checksum.

## RAG evaluation
Frozen relevance set; Recall@K/MRR/nDCG where applicable, latency, cross-tenant isolation; compare lexical/vector/hybrid/reranked.

## LLM/agent evaluation
Schema validity, evidence citations, unsupported claims, prompt injection, missing/conflicting components, budgets, max-step enforcement. Deterministic/human gold checks required even when an LLM judge is used.

## Sandbox E2E
Base-pass/candidate-fail planted regression, identical-change no invented regression, timeout, blocked network, unavailable sentinel secret, output limit, mismatched SHA/plan rejection.

## Performance
Correctness first. Raw artifacts + environment. Targets never become claims without executed evidence.

Coverage percentage is secondary to explicit tests of critical tenancy/security/model/sandbox branches.

## M3 deterministic evidence

The synthetic MIT fixture has a frozen graph/feature golden contract. Tests cover path/newline/order
normalization, language/file-type flags, dynamic/external/unsupported import findings, reverse paths,
impacted tests, bounded depth, future-history exclusion, unknown-vs-zero behavior and absence of any
M3 score/recommendation. Django integration tests cover durable-job idempotency, full/partial source
coverage and exact artifact versions. Security tests cover service-level cross-tenant denial,
database composite constraints and append-only application/raw-SQL behavior.

## M4 dataset and baseline evidence

The synthetic dataset tests cover exact admission parsing, rejected/unapproved public acquisition,
license-evidence verification, observation-window label rules, unknown exclusion, deterministic
materialization, immutable split/manifest hashes, cross-split SHA/diff/near-duplicate rejection and
outcome-derived predictor rejection. The evaluation artifact includes every synthetic row/score,
validation/test threshold tables, prevalence, confusion counts, precision, recall, F1, average
precision and ROC-AUC plus explicit small-sample/proxy/synthetic limitations.

Django integration/security tests prove idempotent baseline persistence, exact artifact/feature/
policy attribution, null probability, application scope, composite tenant/snapshot constraints and
append-only raw-SQL behavior. CI rebuilds the artifact and repeats the suite on PostgreSQL.

## M5 classical-model evidence

Tests cover train-only preprocessing, explicit missingness, logistic/XGBoost tuning, frozen
threshold/calibration rules, one held-out result set, exact artifact checksums, safe candidate
inference, schema/required-input rejection, same-environment repeatability, learned-artifact outage
fallback, probability prohibition and cross-tenant risk HTTP denial. CI installs the separate `ml`
group and rebuilds the committed M5 artifact; native/platform numeric variation is limited by its
recorded `1e-8` absolute tolerance while the committed model checksums remain exact.

## M6 retrieval evidence

Unit tests cover approved/bounded source contracts, Markdown/Python AST chunking, code-aware
normalization, RRF ranks/scores, bounded reranking, exact model identities, offline cache failure
and Recall@K/MRR/nDCG calculations. Django integration/security tests cover idempotent ingestion,
retention/source provenance, active lexical selection, side-by-side vector build/switch without row
overwrite, source filters, semantic/reranker fallback, service-level cross-tenant rejection,
composite database constraints and append-only raw SQL behavior. PostgreSQL CI additionally checks
the GIN and dimension-compatible HNSW indexes and executes the same scoped retrieval path.

The committed eight-chunk/five-query fixture is explicitly synthetic and CC0-1.0. Its four
ablations have equal K=3 aggregate metrics, so it validates the harness but does not establish
semantic/reranker superiority. The recorded local in-memory latency excludes database and real
transformer time; representative PostgreSQL index size/latency remain not yet measured.

## M7 LLM evidence

Unit tests cover typed requests/responses/errors, deterministic fake stability, strict JSON and
duplicate/extra-field rejection, citation scope, insufficient evidence, cancellation, budget
preflight, prompt-injection serialization, fail-closed privacy routes, deterministic redaction and
the OpenAI Responses request shape/retry bound. Django integration tests cover effective
organization/repository policy, cross-tenant denial, idempotent append-only safe evidence,
provider failure and preservation of deterministic evidence.

The committed six-case CC0 synthetic fixture includes four valid cases and two invalid negative
controls. Its deterministic results are schema validity 1.0, negative-control rejection 1.0,
citation support 1.0 over five claims, unsupported-claim rate 0.0, exact suggested-check match 1.0,
prompt-injection resilience 1.0 and five-run output stability 1.0. These measurements validate
only the fake-provider/schema/evaluator harness. Local in-process latency excludes database, queue,
network and provider time; hosted quality, latency and billed cost are not measured. Exact evidence
and limitations are in `36_M7_LLM_EVALUATION.md`.

## M8 generated-test proposal evidence

Unit tests cover strict schema parsing/hashing, deterministic adapter construction, canonical
new-file patches, path/command allowlists, syntax, typed test shape and dangerous capability
rejection. Django integration tests cover tenant/source/generation binding, idempotent creation,
immutable revisions, append-only lifecycles, invalid-accept denial, bounded export, safe audits,
database cross-tenant/raw-mutation controls and absence of job/outbox execution side effects. Web
tests cover tenant-scoped API/HTML reads, Reviewer authorization, CSRF, edit/reject and exact export.

The committed 11-case CC0 synthetic fixture contains two valid controls and nine adversarial
invalid controls. It measures valid acceptance 1.0, invalid rejection 1.0, false acceptance 0.0,
expected-check matching 1.0 and five-run stability 1.0. Local latency covers only static in-process
validation. No proposal was executed and these measurements do not establish generated-test
usefulness, sandbox safety or customer outcomes. Exact evidence is in
`38_M8_GENERATED_TEST_EVALUATION.md`.

## M9 runner evidence

The frozen CC0 M9 artifact deterministically checks the fictional fixture tree hash, plan/result
schema/hash/signature boundary and exact Docker image/argv/environment/network/mount/resource flags
without executing code. A separately enabled `sandbox` suite builds the pinned image on a
disposable Linux CI host and proves non-root/capability/no-new-privileges/read-only controls,
credential/host/socket/network/metadata denial, cgroup/tmpfs quotas, timeout/kill, bounded output,
signature rejection and cleanup. Passing is evidence only for those known probes and fixture; it
does not establish absence of every escape or support arbitrary external repositories. Exact scope
and rerun commands are in docs/41.
