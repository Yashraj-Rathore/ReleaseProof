# Project Status

**Current state: M10 differential/mutation verification implemented and CI-validated on 2026-09-02.**

The repository now chains strict M10 base/candidate plans to an exact separately approved M9 plan,
replays one frozen workload under parity, compares selected HTTP/state/event evidence with explicit
masks, evaluates two controlled mutants and persists an immutable `recommendation-fusion-v1`
decision. The accepted ADR-018 fixture-only boundary is unchanged. External/customer repository
execution remains disabled; this is not a universal sandbox or production-readiness claim.

## Next action

Begin M11 (`RP-1001..RP-1006`) semantic-model work from the unchanged M4/M5 dataset and promotion
gates. Do not widen fixture execution or begin M12 agent work.

## M10 evidence

- `releaseproof.differential-plan.v1` binds the exact M9 plan/approval/proposal/input, controlled
  base and candidate revision checksums, image digest, shared resources/environment/workload,
  mask policy and bounded mutation set. Unknown revision/mask/mutation identities fail closed.
- The image-bundled synthetic fixture provides an identical candidate, a planted tax regression,
  a probe timeout, a removed-validation mutant and a forced-tax mutant. Base and candidate receive
  the same approved generated-test input and run in the same disposable container policy.
- `releaseproof.differential-result.v1` records test/probe outcomes, bounded output, selected HTTP
  status/schema/body, state/events, descriptive timing, explicit differences, mutation outcomes,
  limitations, isolation checks and exact plan/result hashes. Masked request/update identifiers do
  not create differences; latency does not trigger a regression decision.
- Immutable `DifferentialPlan`, `DifferentialRun` and `RecommendationDecision` rows have composite
  tenant relationships, append-only database triggers, idempotent writes and exact lineage back to
  the M9 approval and pull-request snapshot.
- The frozen CC0 evaluator passes identical/no-invention, planted-regression, timeout/UNKNOWN and
  base-failure/non-attribution cases. The bounded mutation result is 1 killed and 1 survived (50%);
  it is explicitly not exhaustive or a production-defect claim.
- `recommendation-fusion-v1` evaluates SHIP, REVIEW, HOLD and UNKNOWN branches. Mandatory missing/
  failed evidence is UNKNOWN; deterministic HOLD outranks an LLM SHIP suggestion; every decision
  is advisory-only with `auto_merge=false`.
- Canonical local validation passed **153 tests** with one PostgreSQL physical-index assertion
  skipped and three live infrastructure/sandbox tests deselected. Ruff, strict mypy over 190 source
  files, Django, migration drift, generated docs/inventory and M4-M10 evaluators passed. The
  exact implementation commit `14b133e` passed GitHub Actions run `33680837554`: canonical checks,
  Compose/startup, authoritative PostgreSQL constraints, pinned image build, live M9/M10 sandbox
  sentinels, SeaweedFS and teardown all succeeded. Exact evidence is in docs/43/44.

## M9 evidence

- Docs/40 ranks kernel/runtime escape, secret/socket/mount/network exfiltration, forged policy,
  tenant/stale binding, resource denial, image substitution, hostile output and cleanup threats.
  ADR-018 accepts dedicated rootless Docker only for the frozen fictional fixture and explicitly
  disables arbitrary external repositories.
- `releaseproof.execution-plan.v1` binds the exact snapshot/check-out, proposal/input, frozen
  fixture tree (`70b1ebeb...b4673`), labeled image digest, argv, four constant non-secret env values,
  network `none`, empty mounts, CPU/memory/PID/tmpfs/time/output ceilings and artifact vocabulary.
  Duplicate/extra/tampered fields and signatures fail closed.
- Candidate containers are numeric non-root, read-only, capability-free, no-new-privileges,
  networkless and mountless, with 0.5 CPU, 256 MiB memory, 64 PIDs, bounded tmpfs/log/output and
  inner/outer timeout+kill. The application/Celery boundary neither imports nor invokes runner code.
- Immutable `ExecutionPlan`, `ExecutionApproval` and `ExecutionRun` rows use composite tenant
  constraints/triggers. Reviewer approval separately repeats exact snapshot/proposal/plan hashes;
  result ingest authenticates exact plan/image/attempt, reuses identical duplicates, rejects
  conflicts and records late evidence as stale.
- The frozen CC0 contract/policy artifact passes all ten declared controls and has file SHA-256
  `c1130790da1fc70aa423a5204c6ca5c70b16bcf2b32dcfa5e171d05181d5c759`. It is non-live synthetic
  evidence; the sandbox-marked CI suite
  separately checks host/secret/socket/network/metadata/resource/timeout/output/cleanup behavior.
- The local deterministic suite passed **143 tests**, with one PostgreSQL physical-index assertion
  skipped and live S3/sandbox tests deselected. Ruff, strict mypy (183 source files), Django and M9
  focused checks passed. GitHub Actions run `33639835178` on final M9 commit `ab59029` passed the
  canonical, authoritative PostgreSQL, Compose, pinned-image, live Docker sentinel, SeaweedFS and
  teardown gates.
- M9 adds no Python dependency, mines no data, calls no hosted/paid provider and executes no
  customer repository. Exact threat, evaluation and learning evidence is in docs/40, docs/41 and
  docs/42.

## M8 evidence

- `generated-test-proposal-v1` strictly binds target behavior, rationale, cited evidence, one file
  path/add-only patch, proposed command, expected result, risk, controlled adapter and exact M7
  provider/model/adapter/prompt/source identity. Duplicate/extra/malformed input is rejected.
- `python-fixture-v1` constructs proposals for one `tests/generated/test_*.py` file. Static
  validation checks canonical text, path/patch/command allowlists, Python AST syntax, typed test
  shape and dangerous capabilities without importing or executing code.
- Immutable tenant/source-bound proposal revisions and append-only lifecycle events implement only
  `draft`, `accepted_for_export`, `rejected` and `superseded`. Editing creates a new hash/revision;
  database constraints/triggers reject cross-tenant binding, raw mutation, invalid chains and
  acceptance when the persisted static report is invalid.
- Authenticated API/HTML detail and Reviewer mutations enforce server-derived active-organization
  scope, role checks and CSRF. Export returns the accepted patch with no-store/hash/correlation
  headers. Acceptance/export creates neither `AnalysisJob` nor `OutboxEvent` and cannot represent
  execution approval.
- The 11-case CC0 synthetic harness has two valid controls and nine adversarial invalid controls.
  It records valid acceptance 1.0, invalid rejection 1.0, false acceptance 0.0, expected-check
  matching 1.0 and five-repeat stability 1.0. These are controlled contract measurements, not
  generated-test usefulness, sandbox safety or customer outcomes.
- Evaluation root hash is
  `d4c2c21778b297642a391f2d1ae6d9faa1a1e4fa53ce8d9c149dcda68f131361`. Local static-suite
  latency recorded median 8.3893 ms/p95 13.3381 ms; it excludes database, provider, queue, patch,
  test-runner, container and network time.
- The canonical local suite passed **123 tests**, with one PostgreSQL physical-index assertion
  skipped and the live S3 contract deselected. Ruff, strict mypy and Django/migration checks passed;
  CI supplies authoritative PostgreSQL/S3 and container evidence for the pushed revision.
- M8 added no dependency, called no hosted provider, downloaded no model, applied no patch and
  executed no generated/untrusted code. Exact evaluation and learning evidence are in docs/38 and
  docs/39.

## M7 evidence

- `analysis-suggestion-v1` separates cited grounded risks, visibly uncertain hypotheses, requested
  tests, missing information and explicit insufficient-evidence behavior. Strict parsing rejects
  malformed/extra/duplicate fields, invalid vocabularies and citations outside the server-built
  context.
- The source-controlled prompt and schema hashes are
  `de5399fe7640da726411cfcd0dadad0e5e58b6423202590458e35a95a82a0374` and
  `9fcf0e4be678643081726e579e2ed6df5ac17a45c5598c0c6c23ea0151a5f296`.
- Immutable organization/repository `HostedLLMPolicy` rows cover local/hosted routes, provider/
  model/content/region allowlists, size/token/cost budgets, redaction, reviewed training/retention/
  storage facts, approver role and timeout/retry bounds. Missing or incompatible facts deny hosted
  transmission; composite database constraints reject cross-tenant policy scope.
- The OpenAI adapter pins `openai==3.6.0` and `gpt-5.4-mini-2026-03-17`, uses Responses strict JSON
  Schema with `store=false`, no tools, explicit maximum output and a bounded retry policy. Pricing
  and contractual facts are externally versioned; response-storage disabled is not called zero
  retention.
- Tenant-scoped analysis persists only safe status/decision hashes, strict output, citations,
  exact prompt/schema/provider/model/adapter/SDK identities, usage and elapsed time. It excludes
  source/prompt text, raw responses, hidden reasoning, credentials and arbitrary exception text.
  Duplicate requests reuse the same evidence item; denial/failure does not erase prior evidence.
- The six-case CC0 synthetic harness records schema validity 1.0, negative-control rejection 1.0,
  citation support 1.0 over five claims, unsupported-claim rate 0.0, exact suggested-check match
  1.0, prompt-injection resilience 1.0 and five-repeat stability 1.0. These are deterministic fake
  contract measurements, not hosted-model or customer-quality results.
- Evaluation root hash is
  `5e4f7abc185842fc914b58872ca42971bef4641d6cc81d04ab7dce6564c3eca4`. Local in-process
  fake-suite latency recorded median 1.8031 ms/p95 3.2425 ms and excludes database, queue, network
  and provider time. Hosted latency/cost are not measured.
- The canonical local suite passed **101 tests**, with one PostgreSQL physical-index assertion
  skipped and the live S3 contract deselected. Ruff, strict mypy, Django/migration, M4/M5/M6/M7,
  master-spec and inventory validation passed; CI supplies the authoritative PostgreSQL/S3 run.
- No model weights, public/customer source or paid/hosted provider were contacted, and no untrusted
  repository code was executed. Exact evaluation and learning evidence are in docs/36 and docs/37.

## M6 evidence

- `KnowledgeDocument`, `KnowledgeChunk`, versioned lexical profiles/rows and 384-dimensional
  embedding profiles/rows are organization/repository bound. Composite PostgreSQL foreign keys and
  SQLite test triggers reject mismatched repository/document/chunk/profile relationships; source
  and index rows are append-only.
- `source-aware-chunker-v1` uses Markdown headings, inert Python AST boundaries and bounded
  fallback chunks. `postgres-simple-code-v1` uses PostgreSQL `simple` plus
  `code-aware-normalizer-v1`; the forward migration creates GIN and cosine HNSW physical indexes.
- The selected embedding is `sentence-transformers/all-MiniLM-L6-v2` revision `1110a243...`, 384
  dimensions, and the reranker is `cross-encoder/ms-marco-MiniLM-L6-v2` revision `4bebbd56...`.
  Apache-2.0 license metadata and exact safetensors checksums are recorded. Real adapters are
  offline-only and fail closed on a missing/mismatched local artifact.
- `rrf-v1-k60` preserves lexical/vector scores and ranks. Missing semantic evidence falls back to
  lexical retrieval; reranker failure preserves hybrid ordering. No repository text controls a
  provider, tool, authorization or network decision.
- The frozen CC0 synthetic fixture has eight chunks and five graded queries. At K=3, lexical,
  deterministic fake vector, hybrid and deterministic fake-reranked variants all measure Recall
  0.90, MRR 1.00 and nDCG 0.950262129022. Equality does not prove semantic/reranker value, so the
  real reranker is disabled by default.
- The raw artifact root hash is
  `f7e9009bdc7547b3fb677013b0f7752d5a28ea1071f92a17754d36af3d107b70`. Recorded local in-memory
  full-ablation latency is median 6.930450 ms/p95 7.680900 ms; it excludes PostgreSQL and real-model
  time. Representative database index size/latency remain not yet measured.
- The canonical local suite passed **86 tests** with one PostgreSQL physical-index assertion
  skipped and the live S3 contract deselected. Ruff and strict mypy passed for 156 source files;
  Django/migration/M4/M5/M6/doc/inventory checks passed. M6 coverage includes ingestion,
  provenance, side-by-side activation, component scoring, fallback, exact artifacts, metrics,
  database immutability and cross-tenant denial. CI supplies the authoritative PostgreSQL/S3 run.
- No model weight, public/customer source or paid/hosted provider was downloaded or contacted, and
  no untrusted repository code was executed.

## M5 evidence

- The separate `ml` group locks NumPy 2.5.2, pandas 3.0.5, scikit-learn 1.9.0 and
  `xgboost-cpu` 3.4.1 on CPython 3.13.15. Official release/compatibility evidence is recorded in
  docs/26; the exact transitive environment is in `uv.lock`.
- `classical-preprocessor-v1` fits only on six training rows, binds exact `change-features-v1`,
  records imputation/missingness/scaling and has hash
  `41f9072f1e5d34aa1e934788fe1026b096222482534acca308ce7dc6b7ddcd33`.
- Logistic and XGBoost configurations plus score thresholds use train/validation only. The final
  test read occurs after target, costs, thresholds, calibration candidates, Brier/reliability/ECE
  rules, sample minimums and tolerances are declared.
- Both calibration candidates are not attempted because four validation rows fail the frozen
  200-row/50-per-class gate. Calibrated probability is null and probability display is prohibited.
- On four synthetic held-out rows, logistic has TP=1, FP=1, TN=1, FN=1, F1=0.50, AP=0.50 and
  ROC-AUC=0.25. XGBoost has TP=1, FP=2, TN=0, FN=1, F1=0.40, AP=0.41666667 and ROC-AUC=0.25.
  These unstable fictional measurements validate only the harness.
- The 56,530-byte artifact `models/public/m5_classical_ml_v1.json` names training commit
  `e63fcff3b2afd18775cd3a1cb01bb4688db316a3` and root hash
  `cb552fd83b257d67248d804c931cf604942d76bac245069b64f58048bfa9a8d6`.
  Same-environment rebuild is byte-identical; cross-platform numeric comparison is bounded at
  `1e-8` after excluding native bytes/platform identity.
- Neither candidate beats/complements the heuristic defensibly. `deterministic-heuristic-v1`
  remains active and is the explicit rollback. Missing/invalid learned artifacts report baseline
  fallback instead of erasing deterministic evidence.
- Authenticated model/risk API and HTML views expose exact versions, score components, limitations
  and no probability. Tests cover cross-tenant snapshot denial, checksum/schema/input failures and
  fallback behavior.
- The canonical local suite passed **72 tests** with one live S3 test deselected; Ruff and strict
  mypy passed for 141 source files, and Django/migration/M4/M5/doc/inventory checks passed.
- No public repository/customer data was acquired, no pretrained model was downloaded, no paid or
  hosted provider was called, and no untrusted repository code was executed.

## M4 evidence

- `source-admission-v1` records the synthetic repository numeric identity, fixture URL, MIT
  license-evidence hash/version, terms review, allowed local acquisition/fields/artifacts,
  retention/redistribution/attribution rules, `as_of`, 30-day observation window, reviewer and
  record limits. No public repository or customer data was accessed.
- `proxy-label-rule-v1` keeps revert/hotfix/follow-up/required-check signals as proxies. Complete
  no-proxy windows become proxy negatives; ambiguous/incomplete observations stay unknown.
- `releaseproof-m4-synthetic-v1` contains 16 deliberately synthetic rows: 6 train, 4 validation,
  4 held-out test and 2 excluded unknowns. Seven included rows are positive proxies and seven are
  negative proxies; this designed 50% prevalence is not a real population estimate.
- `temporal-split-v1` and `leakage-report-v1` freeze assignments and pass checks for prediction-time
  features, observation completeness, exact schema, author/outcome exclusion and no cross-split
  head SHA, diff hash or normalized near-duplicate. One fixture repository means repository
  holdout is not measured and is an explicit limitation.
- Manifest hash `eab561cbce6cc9986e5b8d9a248b268e3709407dff7f23b111c36c932dd86456`
  names extraction code commit `3448b1f879682d2b12a212d4c82d8fee87e33a12`; split hash is
  `81d51ed7011c86744f2cf4bff15cb98bb1aa440b1c81ece921ed9b4a21f0c11b`.
- `deterministic-heuristic-v1` uses threshold 30 selected from validation only. The four-row
  synthetic held-out confusion is TP=2, FP=2, TN=0, FN=0: precision 0.50, recall 1.00,
  F1 0.66666667, average precision 0.41666667 and ROC-AUC 0.125. The sample is too small and
  fictional for product/incident claims; calibration is not applicable because this is a score.
- `RiskScore` persists exact feature/artifact/policy attribution, contributions, score/band or
  UNKNOWN and a null probability. Composite tenant/snapshot/feature constraints and append-only
  triggers passed on SQLite; CI repeats them against PostgreSQL.
- The canonical local suite passed **62 tests** with one live S3 test deselected; Ruff and strict
  mypy passed for 136 source files, and Django/migration/artifact reproducibility checks passed.

## M3 evidence

- Diff, feature, graph, history and risk-factor contracts are versioned and checksummed; inputs,
  file sizes, graph depth/edges and output counts are bounded with explicit truncation or missing
  reasons.
- The static analyzer uses Python AST without importing or executing repository code. Dynamic
  imports, unsupported languages, parse errors and unavailable/partial source trees remain visible
  findings rather than silently complete evidence.
- Historical features enforce `observed_at < prediction_time`; absent history and incomplete graph
  facts remain null with reasons rather than becoming misleading zeroes. Author familiarity is an
  opaque aggregate, not a display identity.
- Append-only `ChangeFeatureSet` and `EvidenceItem` rows are organization-, snapshot- and
  feature-bound, with application validation plus PostgreSQL and SQLite tenant/immutability
  controls.
- Golden-fixture, unit, persistence, duplicate-delivery and cross-tenant tests passed in the local
  deterministic suite: **55 tests passed**, with the separate live S3 contract deselected.
- Ruff and strict mypy passed for 123 source files. Django checks and migration-drift checks passed.
- The local Docker Desktop daemon was unavailable for a fresh authoritative-database run. CI now
  starts the pinned services and runs the complete deterministic suite against PostgreSQL before
  the S3 contract; the GitHub Actions result is the remote database evidence for this revision.
- No model was downloaded or trained, no public/customer data was mined, no hosted provider was
  called, and no untrusted fixture source was executed.

## M2 evidence

- Organizations, memberships/roles, GitHub installations/repositories, webhook receipts,
  immutable snapshots, authoritative jobs/outbox rows and append-only audit records have forward
  migrations.
- Composite organization/parent constraints and immutable-record triggers passed on SQLite and
  PostgreSQL 18.6. The full deterministic suite passed **44 tests** on each backend; the separate
  live S3 test was intentionally deselected in these M2 runs.
- Tests cover session/CSRF behavior, login throttling and cache failure, role/IDOR denial, HTTP,
  Celery, admin and management-command scope, signed/tampered/duplicate webhooks, bounded input,
  lifecycle events, immutable checksummed snapshots, broker recovery, bounded retries, duplicate
  task delivery and stale-safe fake advisory publication.
- Strict mypy passed for 107 source files; Ruff, Django checks and migration-drift checks passed.
- GitHub CLI authentication and remote `main` access were repaired, and the configured pre-commit
  and pre-push hooks are installed locally.
- No live GitHub API was called, no installation access token was persisted, and no real check was
  posted. The live snapshot/token/check adapters remain not yet implemented or validated.

## M1 evidence

- `uv sync --frozen --group dev` resolved the committed lock with CPython 3.13.15.
- Ruff format/lint passed; strict mypy passed for 64 source files.
- The deterministic suite passed 25 tests with the one infrastructure test deselected.
- The live SeaweedFS suite passed 1 contract test after authenticated, idempotent bucket bootstrap.
- Django system checks and migration-drift checks passed; only Django's built-in migrations were
  applied to the disposable local PostgreSQL database.
- Compose reported PostgreSQL/pgvector, Redis, and SeaweedFS healthy. Runtime probes reported
  PostgreSQL 18.6, pgvector 0.8.6, and SeaweedFS 4.44; Redis returned authenticated `PONG`.
- `/health/live` and `/health/ready` returned their deterministic healthy payloads with real
  PostgreSQL; the automated failure-path test returns 503 without database details.
- The exact HTMX 2.0.10 checksum test passed, and the network-free fake smoke was repeatable.

The generated inventory now normalizes UTF-8 line endings before hashing, allowing the same
committed manifest to be checked from Windows and Linux GitHub-hosted runners.
Local S3 credential files remain owner-only; CI relaxes permissions only on its ephemeral file
generated from public `.env.example` values so the pinned non-root SeaweedFS image can read it.

The local Docker host was Engine 24.0.6 / Compose 2.23.0 rather than the documented
29.7.2 / 5.4.0 baseline. The digest-pinned services passed on this older host, but that does not
substitute for a later run on the documented host baseline. The GitHub-hosted workflow is defined,
and its remote M2 result is tracked in GitHub Actions.

| Milestone | Status |
|---|---|
| M0 assessment | Complete — 2026-08-27 assessment plus contradiction/ambiguity correction |
| M1 foundation | Complete — RP-0001..RP-0005 |
| M2 tenancy/GitHub | Complete â€” RP-0101..RP-0106 |
| M3 change intelligence | Complete - RP-0201..RP-0206 |
| M4 dataset/baseline | Complete - RP-0301..RP-0306 |
| M5 classical ML | Complete - RP-0401..RP-0406; candidates not promoted |
| M6 RAG | Complete - RP-0501..RP-0506; real reranker disabled pending representative evidence |
| M7 LLM evidence | Complete - RP-0601..RP-0606; deterministic fake remains default |
| M8 generated tests | Complete - RP-0701..RP-0704; export only, no execution approval |
| M9 sandbox | Complete - RP-0801..RP-0805; fixture-only boundary, live CI validated |
| M10 differential | Complete - RP-0901..RP-0905; fixture-only boundary, live CI validated |
| M11 PyTorch/HF | Not started |
| M12 LangGraph | Not started |
| M13 MLflow/governance | Not started |
| M14 security/ops | Not started |
| M15 containers/CI/model serving | Not started |
| M16 demo/pilot | Not started |
| M17 final review | Not started |
