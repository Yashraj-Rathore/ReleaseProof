# Changelog

## Unreleased
### Added
- Initial implementation-ready ReleaseProof specification package.
- Product, architecture, database, APIs, GitHub, change intelligence, dataset, ML, semantic-model, RAG, LLM, agent, sandbox, UX, security, testing, MLOps, observability, DevOps, performance, commercialization, runbook, interview, learning and pilot specifications.
- Codex repository instructions, prompts, backlog, ADRs and definition-of-done templates.
- ADR-016 selecting maintained SeaweedFS 4.44 for the bounded local S3 contract.
- ADR-017 defining tenant isolation through server-derived scope, application services and database constraints before optional RLS.
- M1 repository tooling with a Python 3.13.15/uv lock, Ruff, mypy, pytest, pre-commit, and pinned CI actions.
- Pinned PostgreSQL/pgvector, Redis, and SeaweedFS Compose services with persistent local volumes and health checks.
- The canonical ten-app Django modular-monolith skeleton with liveness/readiness endpoints and Celery configuration.
- Provider-neutral GitHub, advisory-LLM, and bounded object-storage seams with deterministic fakes.
- A boto3 S3 adapter, SeaweedFS contract test, idempotent bucket bootstrap, and licensed synthetic fixture repository.
- Vendored HTMX 2.0.10 with a verified SHA-256 checksum.
- Deterministic generation of the Git-ignored SeaweedFS credential config from an explicit local environment file.
- M2 organizations, memberships/roles, tenant-scoped services, session organization context and
  Owner/Admin repository lifecycle authorization.
- CSRF-protected session login/logout with hashed-key throttling and fail-closed cache outage
  behavior; no browser access-token storage.
- Tenant-bound GitHub installations/repositories with least-privilege permission validation,
  credential references and a redacted bounded in-memory installation-token cache contract.
- Signed, size/schema/action-bounded GitHub webhook ingestion with immutable delivery receipts,
  normalized checksummed PR snapshots and installation/repository lifecycle handling.
- PostgreSQL-authoritative ingestion jobs, identifier-only transactional outbox rows, bounded relay
  retries, recovery tooling and idempotent Celery worker behavior.
- Database composite tenant foreign keys and append-only triggers for PostgreSQL and the SQLite
  test backend, plus safe DRF error envelopes and scoped admin/management boundaries.
- Stale-safe advisory report contract and deterministic GitHub/task publisher fakes that make no
  remote or paid-provider calls.
- M3 versioned diff normalization, exact prediction-time feature schema, bounded static Python
  import graph, deterministic blast radius, strictly pre-change history and cited risk factors.
- Append-only tenant-bound feature/evidence persistence, durable-job integration and a richer MIT
  synthetic golden fixture with explicit dynamic/unsupported-language behavior.
- M4 source-admission, proxy-label, frozen temporal-split, leakage-check and feature-materialization
  contracts with a 16-row synthetic MIT fixture and byte-reproducible raw evaluation artifact.
- The first transparent deterministic heuristic score/band and validation-selected threshold
  policy, persisted as append-only tenant/snapshot/feature-bound risk evidence with no probability.
- M5 train-only tabular preprocessing, logistic-regression and XGBoost CPU candidate training,
  validation-only configuration/threshold selection and one frozen held-out synthetic evaluation.
- A checksum-bound `classical-risk-artifact-v1` with exact runtime/data/feature/preprocessor/model
  lineage, raw predictions/metrics, calibration abstention, promotion/rollback decision and model
  card.
- Authenticated tenant-scoped current-model and snapshot-risk API/HTML reads with evidence-backed
  components, explicit non-probability wording and safe deterministic fallback when learned
  artifacts are missing or invalid.
- M6 approved evidence ingestion with Markdown-heading, inert Python-AST and bounded fallback
  chunking; every document/chunk retains tenant, repository, source/version/hash and retention
  provenance.
- Versioned PostgreSQL `simple` FTS rows, a 384-dimensional pgvector table, forward GIN/HNSW
  indexes and transactionally activated side-by-side lexical/embedding profiles.
- Deterministic `rrf-v1-k60` hybrid fusion with component ranks/scores plus bounded optional
  cross-encoder reranking and explicit provider/model mismatch fallback.
- Offline checksum-verified sentence-transformers embedding/reranker adapters and separately named
  deterministic fakes; exact Hugging Face revisions, licenses, dimensions and safetensors hashes.
- A frozen CC0 synthetic retrieval relevance set, raw per-query Recall@K/MRR/nDCG ablations,
  bounded latency evidence, failure modes, activation decision and M6 Owner Learning Note.
- M7 typed advisory-LLM requests/responses/errors, deterministic fake, strict cited suggestion
  schema and versioned source-controlled prompt/schema content hashes.
- Immutable organization/repository hosted-LLM policy with fail-closed provider/model/content/
  region/training/retention/storage routing, bounded redaction and database tenant/immutability
  enforcement.
- A pinned OpenAI Responses adapter with strict JSON Schema, disabled response storage, no tools,
  explicit output/cost/timeout/retry bounds and safe external pricing/contract configuration.
- Tenant-scoped idempotent append-only LLM evidence that preserves deterministic evidence and never
  persists prompt/source text, raw provider output, hidden reasoning, secrets or arbitrary errors.
- A frozen six-case CC0 synthetic grounding suite, raw evaluation artifact and M7 Owner Learning
  Note covering schema/citation/unsupported-claim/stability/injection/cost/latency evidence.
- M8 strict generated-test proposal contracts and a deterministic controlled-Python-fixture
  adapter that builds inert add-only patches and performs parse/format/type-shape/safety checks.
- Tenant-bound immutable proposal revisions, append-only draft/accept/reject/supersede events,
  composite database constraints/triggers, safe audits and idempotent lifecycle services.
- Reviewer/CSRF-protected API and server-rendered review/edit/export flows that explicitly separate
  export acceptance from M9 execution approval and never create execution jobs.
- A frozen 11-case CC0 adversarial proposal suite, raw evaluation artifact and M8 Owner Learning
  Note covering schema/static checks, stability, non-execution and limitations.
- An accepted RP-0801 threat review and ADR-018 selecting dedicated rootless Docker for only the
  exact fictional fixture while keeping arbitrary external repository execution disabled.
- Strict HMAC-authenticated M9 execution input/plan/result contracts with immutable hashes, pinned
  fixture/image/argv/environment/network/mount/resource/artifact policies and bounded output.
- Tenant-bound immutable execution plans, separate Reviewer/CSRF execution approvals and append-only
  idempotent result evidence with stale/timeout/kill/isolation/cleanup facts and database triggers.
- A separate Docker CLI runner/image using non-root/read-only/no-capability/no-new-privileges/
  no-network/no-host-mount controls, cgroup/tmpfs/time/output limits and mandatory cleanup.
- Frozen synthetic M9 policy evidence plus an explicit live CI sandbox suite for credential/host/
  socket/network/metadata/resource/timeout/output/signature/cleanup sentinels and an Owner Learning
  Note.

### Changed
- Recorded the verified Python 3.13.15/uv/Django/data-service/tooling pins and milestone-gated later dependency snapshots.
- Canonicalized the ten RP-0003 Django module names and policy ownership.
- Made PostgreSQL jobs plus a transactional outbox authoritative across Redis/Celery transport loss.
- Separated generated-test acceptance/export from M9 execution authorization.
- Assigned raw deterministic risk factors to M3 and the first composite evaluated heuristic to M4.
- Added public-dataset source admission, frozen calibration-decision, FTS/embedding index, hosted-provider retention, runner-backend and conditional model-serving gates.
- Replaced vague M13/M14 dependencies with explicit milestone prerequisites.
- Added Boto3 1.43.81 to the Prompt 1 runtime baseline for the ADR-016 S3 adapter.
- Made SeaweedFS readiness wait for a registered writable volume before authenticated S3 bootstrap.
- Made the generated file inventory normalize UTF-8 line endings before hashing so Windows and
  Linux checkouts validate the same committed source bytes.
- Kept generated local S3 credentials owner-only while making only CI's ephemeral, public-example
  credential file readable by the pinned SeaweedFS container's non-root user.
- Upgraded pull-request snapshots to `github-pr-snapshot-v2` for optional bounded commit count and
  opaque author familiarity input without exposing identity as a predictor.
- Added an authoritative PostgreSQL test pass to CI after Compose readiness so database-specific
  tenant and immutability controls cannot be inferred only from SQLite tests; the step uses an
  explicit public test-only webhook signing value while `.env.example` remains secret-free.
- Resolved the fixture runner's allowlisted `python` command through the image's current
  interpreter so its deliberately minimal, secret-free child environment does not require `PATH`;
  invalid runner output reports a bounded category, with a sanitized/length-bounded daemon detail
  allowed only for the explicit controlled-fixture ephemeral-CI profile.
- Disabled compression for the M9 Docker `local` log driver because the bounded one-file rotation
  policy is incompatible with that driver's default compression setting.
- Added the frozen M4 artifact rebuild to the canonical validator and kept NumPy, pandas,
  scikit-learn and XGBoost deferred until a learned-model milestone needs them.
- Reverified and locked NumPy 2.5.2, pandas 3.0.5, scikit-learn 1.9.0 and CPU-only XGBoost 3.4.1
  in the M5 `ml` group; CI and the canonical validator now reproduce the M5 model artifact.
- Kept `deterministic-heuristic-v1` active because the learned candidates use tiny one-repository
  synthetic data, fail the frozen calibration sample gate and do not add defensible product value.
- Added pgvector Python 0.5.0 to the runtime and sentence-transformers 6.0.0 to an optional semantic
  group without permitting implicit model downloads or changing the later M11 training decision.
- Kept the real M6 cross-encoder disabled because the synthetic fake-provider ablation showed no
  aggregate retrieval improvement and cannot establish representative value/latency.
- Reverified and locked `openai==3.6.0` in the optional `ai` group with immutable model snapshot
  `gpt-5.4-mini-2026-03-17`; omitted LangChain because the bounded adapter needs no additional
  framework, and kept hosted routing disabled without an explicit compatible tenant policy.
- Kept the dependency lock unchanged in M8: standard-library static parsing plus existing
  Django/DRF controls are sufficient, while execution tooling remains deferred to M9 threat review.
- Kept the dependency lock unchanged in M9: the separate runner uses the standard library, Docker
  CLI and the already pinned fixture pytest version. The runner is not placed beside application
  services in Compose and the application host receives no Docker socket.

### Evidence status
- M1 implementation evidence is recorded in `PROJECT_STATUS.md`; no product performance, ML quality,
  customer outcome, production-readiness, or sandbox-security claim exists yet.
- M2 evidence is recorded in `PROJECT_STATUS.md`: 44 deterministic tests passed on both SQLite and
  PostgreSQL. Live GitHub token minting/API/check posting remains unvalidated and is not claimed.
- M3 evidence is recorded in `PROJECT_STATUS.md`: 55 local deterministic tests cover the versioned
  change-intelligence contracts and CI provides the authoritative PostgreSQL/S3 gate. No composite
  baseline, learned-model result, customer outcome, or sandbox claim is made.
- M4 evidence is recorded in `PROJECT_STATUS.md`; its metrics come only from a tiny balanced
  synthetic fixture and are not product-performance, probability, incident or customer claims.
- M5 evidence is recorded in `PROJECT_STATUS.md` and docs/32; learned-model figures remain tiny
  synthetic harness measurements, probability is disabled and neither candidate is promoted.
- M6 evidence is recorded in `PROJECT_STATUS.md` and docs/34; retrieval figures are synthetic
  harness measurements, real weights were not executed, and no customer/public quality claim is
  made.
- M7 evidence is recorded in `PROJECT_STATUS.md` and docs/36; its perfect frozen-fixture figures
  validate only the deterministic fake/schema harness. No hosted provider/customer source was
  contacted and no hosted quality, real latency, billed cost or zero-retention claim is made.
- M8 evidence is recorded in `PROJECT_STATUS.md` and docs/38; its perfect frozen-fixture figures
  validate only the controlled schema/static-filter harness. No proposal was executed, committed or
  approved for M9 execution, and real-repository usefulness/sandbox safety are not claimed.
- M9 evidence is recorded in `PROJECT_STATUS.md` and docs/40-42. Deterministic policy and known live
  fixture sentinels do not prove absence of all container escapes; arbitrary external repository
  execution and general production readiness remain explicitly unvalidated.
