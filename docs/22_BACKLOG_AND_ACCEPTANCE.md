# 22 — Backlog and Acceptance

This is the canonical implementation backlog. **Codex must implement only assigned issue IDs.**
An issue is complete only when its acceptance statement below, linked numbered docs, ADRs, and
`templates/definition-of-done.md` are satisfied. Any measured metric must be backed by a reproducible
artifact; a placeholder target is not an achieved result.

## Global acceptance rules

- Tenant isolation, provenance, idempotency, bounded inputs, auditability, and safe failure behavior are cross-cutting requirements.
- `UNKNOWN` / insufficient evidence is valid and preferable to fabricated certainty.
- AI output is advisory. ReleaseProof never merges or deploys a customer's code in the planned release.
- Untrusted repository code may not execute on the web/API/Celery host.
- Dataset labels, training/test boundaries, model versions, prompts, embedding/reranker versions and evaluation fixtures are versioned.
- Source/docs/status/changelog and the generated master spec stay synchronized.
- Every ML/LLM/RAG/agent milestone produces the Owner Learning Note required by `AGENTS.md`.


## M1 — Foundation

### RP-0001 — Repository and Python tooling foundation

**Acceptance:** Pin a compatible Python baseline after Prompt 0 verification; configure package management, linting, typing, tests, pre-commit, editor settings, and deterministic local commands.

### RP-0002 — Local infrastructure baseline

**Acceptance:** Define Docker Compose services for PostgreSQL/pgvector, Redis, and SeaweedFS 4.44 exposing the bounded S3 contract from ADR-016, with exact image tags and OCI manifest digests, health/readiness checks, persistent volumes, safe local credentials, an idempotent bucket bootstrap, and documented non-destructive stop versus explicit destructive reset semantics.

### RP-0003 — Modular Django package boundaries

**Acceptance:** Create the Django project and explicit modules for identity, organizations, repositories, changes, evidence, risk, retrieval, analysis, verification, and audit without premature microservices.

### RP-0004 — Deterministic provider fakes and fixture repository

**Acceptance:** Provide fake GitHub/LLM/object-storage adapters and a small licensed fixture repository so core tests and the demo do not require paid providers or arbitrary remote code.

### RP-0005 — CI and documentation synchronization

**Acceptance:** Add baseline CI for format/lint/type/test/doc-sync and create the generated-master-spec check.


## M2 — Tenancy, Identity, and GitHub Ingestion

### RP-0101 — Organizations and memberships

**Acceptance:** Persist organizations, memberships, roles, repository bindings and lifecycle states; implement ADR-017 scoped services/querysets, object authorization, organization-consistent unique/composite foreign-key constraints and cross-context tenant-isolation tests.

### RP-0102 — Browser session authentication and CSRF

**Acceptance:** Implement secure Django session authentication, CSRF-protected mutations, role checks, login throttling, and no browser token storage.

### RP-0103 — GitHub App installation model

**Acceptance:** Represent GitHub installations/repositories with least-privilege permissions, revocation and tenant binding; store only the GitHub App private-key/secret-manager reference required to mint installation tokens. Keep short-lived installation tokens in bounded process memory and never persist them in database, cache, logs or task payloads.

### RP-0104 — Signed GitHub webhook ingestion

**Acceptance:** Verify webhook signatures, enforce size/content limits and deduplicate delivery IDs; atomically persist immutable event metadata, authoritative job and transactional outbox entry, then relay to Celery. Prove broker/relay recovery and harmless duplicate task delivery.

### RP-0105 — Immutable pull-request change snapshot

**Acceptance:** Fetch and persist normalized PR metadata, refs, changed files, commit SHAs, CI/check metadata, bounded patches, and a snapshot checksum.

### RP-0106 — GitHub check/status adapter and demo fake

**Acceptance:** Publish an advisory check/report through an adapter; local/demo mode must prove behavior without posting to a real repository.


## M3 — Deterministic Change Intelligence

### RP-0201 — Diff normalization and language detection

**Acceptance:** Normalize changed-file facts, additions/deletions/renames, language/type classification, and bounded diff text with stable schema versioning.

### RP-0202 — Feature schema v1

**Acceptance:** Define deterministic feature names/types/defaults, feature-schema version, provenance, and no label-derived or post-outcome inputs.

### RP-0203 — Python import/dependency graph v1

**Acceptance:** Parse supported Python fixture repositories into a bounded dependency graph with explicit unsupported/dynamic-import behavior.

### RP-0204 — Blast-radius engine v1

**Acceptance:** Compute direct/transitive affected modules, sensitive-area tags, graph depth, and evidence paths deterministically.

### RP-0205 — Historical repository statistics

**Acceptance:** Derive pre-change churn, ownership familiarity, prior failure proxies, file/module change frequency, and temporal windows without future leakage.

### RP-0206 — Human-readable evidence rendering

**Acceptance:** Expose versioned feature values, graph paths, source facts and missing-data indicators as deterministic risk factors. Do not create a composite risk score, threshold recommendation or evaluated heuristic baseline here; RP-0306 owns that artifact.


## M4 — Dataset and Deterministic Baseline

### RP-0301 — Dataset manifest and provenance schema

**Acceptance:** Define dataset source/license, repository/commit boundaries, extraction version, label rule, split assignment, exclusion reasons, checksums, lineage and the per-source approval record required by docs/07, including license/terms evidence, approved acquisition method, `as_of` cutoff and completed observation window.

### RP-0302 — Public/fixture extraction pipeline

**Acceptance:** Build reproducible extraction only from fixture sources or public repositories with an approved source-admission record; enforce the recorded API/rate/retention/redistribution limits and never fabricate customer-like outcomes or silently scrape unsupported data.

### RP-0303 — Proxy-label rules

**Acceptance:** Specify auditable proxy labels such as revert/hotfix/failed-check outcomes, known limitations, uncertainty, and exclusions; do not call proxies production incidents.

### RP-0304 — Leakage-resistant train/validation/test split

**Acceptance:** Use repository-grouped and/or temporal splits so related changes and future facts cannot leak across evaluation boundaries.

### RP-0305 — Feature materialization pipeline

**Acceptance:** Materialize versioned feature rows, target labels, missingness, hashes, and dataset statistics from immutable snapshots.

### RP-0306 — Heuristic baseline and evaluation harness

**Acceptance:** Establish the first composite deterministic rules baseline and versioned threshold policy before training ML; evaluate it on the frozen split and publish raw confusion/threshold artifacts and limitations. It is a score/band, not a probability, so calibration is explicitly not applicable at this milestone.


## M5 — Classical ML Risk Engine

### RP-0401 — Logistic-regression baseline

**Acceptance:** Train, tune only on train/validation, evaluate once on held-out test, persist preprocessing/model metadata, and establish interpretable coefficients.

### RP-0402 — XGBoost risk model

**Acceptance:** Train an XGBoost classifier using the same immutable split and feature schema; compare against logistic and heuristic baselines.

### RP-0403 — Calibration, uncertainty, and thresholds

**Acceptance:** Before final-test inspection, freeze the target population, calibration candidates, Brier baseline, reliability/ECE/binning rules, minimum sample rules and numeric acceptance tolerances selected from validation data and explicit cost assumptions. Evaluate once on held-out test; if the frozen calibration rule fails, prohibit probability wording and retain score/band plus abstention/UNKNOWN behavior.

### RP-0404 — Model-artifact contract

**Acceptance:** Version model artifact, feature schema, dataset manifest, metrics, hash, runtime compatibility, and rollback metadata.

### RP-0405 — Risk-scoring API and UI

**Acceptance:** Serve deterministic model selection and evidence-backed score components without presenting an uncalibrated score as a probability.

### RP-0406 — Reproducibility proof

**Acceptance:** Re-run training/evaluation from the frozen manifest and document expected deterministic/non-deterministic variance.


## M6 — RAG and Historical Evidence

### RP-0501 — Evidence-document ingestion

**Acceptance:** Ingest bounded approved PR summaries, ADRs, incidents/postmortems, runbooks, and docs with source identity, tenant scope, retention, and chunk provenance.

### RP-0502 — PostgreSQL full-text retrieval

**Acceptance:** Implement lexical retrieval using the versioned PostgreSQL `simple` configuration and code-aware normalizer from docs/10, with filters, stable scoring metadata, tenant isolation and a migration/rebuild path for later FTS versions.

### RP-0503 — pgvector semantic retrieval

**Acceptance:** Select and record an exact embedding artifact/revision/dimension, generate through a versioned adapter, store vectors in a dimension-compatible versioned physical index, perform filtered semantic retrieval and prove side-by-side rebuild/switch behavior without overwriting the active index.

### RP-0504 — Hybrid fusion

**Acceptance:** Combine lexical/vector ranks with a documented deterministic fusion method and expose component scores.

### RP-0505 — Cross-encoder reranking

**Acceptance:** Rerank a bounded candidate set with a pinned Hugging Face/sentence-transformer model and safe fallback if unavailable.

### RP-0506 — Retrieval evaluation

**Acceptance:** Create labeled query/evidence fixtures and report Recall@K, MRR/nDCG where meaningful, latency, failure modes, and ablations.


## M7 — Evidence-Grounded LLM Analysis

### RP-0601 — LLM provider abstraction and fake

**Acceptance:** Define typed provider request/response/error contracts, deterministic fake provider, budgets, timeouts, retry policy, and no hidden provider coupling.

### RP-0602 — OpenAI adapter

**Acceptance:** Reverify and pin the exact OpenAI SDK at implementation time; use the official recommended API pattern with explicit model/config selection, provider-side storage setting, structured output validation, redaction/routing rules, bounded context/time/cost and recorded adapter/SDK versions. Do not claim zero retention unless the tenant/provider contract actually supplies it.

### RP-0603 — Privacy-aware routing policy

**Acceptance:** Implement the versioned policy fields in docs/11 for disable/hosted/local routing, allowed content classes, size, provider/model, training/retention review, region and storage mode; prevent transmission on missing/incompatible policy and record the policy/provider/model decision without logging code.

### RP-0604 — Versioned prompts and schemas

**Acceptance:** Store prompt/template/schema versions in source control and persist only safe structured outputs and evidence references.

### RP-0605 — Grounded change analysis

**Acceptance:** Produce risks, hypotheses, requested tests, cited evidence IDs, confidence category, and explicit insufficient-evidence behavior.

### RP-0606 — LLM evaluation suite

**Acceptance:** Measure schema validity, citation support, unsupported-claim rate, stability/cost/latency on frozen fixtures; do not use model self-grading alone.


## M8 — AI-Generated Test Proposals

### RP-0701 — Fixture test-framework adapter

**Acceptance:** Support generation/validation for the controlled Python fixture repository first; do not claim arbitrary-language universal support.

### RP-0702 — Structured test-proposal schema

**Acceptance:** Require target behavior, rationale, evidence, file path, patch, commands, expected result, risk, and generation metadata.

### RP-0703 — Human approval/rejection workflow

**Acceptance:** Implement immutable proposal revisions and `draft`, `accepted_for_export`, `rejected` and `superseded` transitions. Editing creates a new draft/hash. Acceptance permits export only, never commit or execution; M9 separately owns `execution_approved` and `executed` transitions.

### RP-0704 — Static proposal validation

**Acceptance:** Parse/format/type/safety-check generated test changes before any execution and clearly surface invalid proposals.


## M9 — Isolated Sandbox Runner

### RP-0801 — Runner threat review and trust-boundary signoff

**Acceptance:** Before runner code, document attack paths, kernel/container escape assumptions, secrets/network/filesystem policy, quotas and cleanup, then add an accepted ADR selecting the actual isolation backend and host assumptions. Stop on unresolved Critical/High blockers; if external hostile-code isolation is not justified, restrict M9 to the fictional fixture or defer it explicitly.

### RP-0802 — Versioned execution-plan contract

**Acceptance:** Define allowed image, checkout SHA, commands, environment, resources, timeout, network policy, mounts, expected artifacts, and immutable plan hash.

### RP-0803 — Isolated fixture execution

**Acceptance:** Run only the controlled fixture repository in disposable containers with non-root user, read-only base where possible, no host Docker socket, no secrets, bounded resources/time.

### RP-0804 — Sandbox sentinel tests

**Acceptance:** Prove blocked host access, blocked credential leakage, bounded network policy, timeout/kill, disk/memory/CPU limits, and cleanup.

### RP-0805 — Execution result contract and idempotency

**Acceptance:** Persist safe stdout/stderr excerpts/artifacts, exit facts, timing, image/plan hashes, retries, and duplicate-request behavior.


## M10 — Differential and Mutation Verification

### RP-0901 — Base/candidate environment parity

**Acceptance:** Build base and candidate from controlled immutable SHAs under the same versioned environment/workload contract.

### RP-0902 — Deterministic workload comparison

**Acceptance:** Replay the same approved requests/tests against both versions and record comparable success/failure/latency evidence.

### RP-0903 — HTTP/state differential engine

**Acceptance:** Compare status/schema/selected state/events and explicitly mask known nondeterministic fields.

### RP-0904 — Mutation-testing slice

**Acceptance:** Introduce a bounded mutation set in fixture code and measure whether existing/generated tests kill mutations; report mutation score limitations.

### RP-0905 — Recommendation evidence integration

**Acceptance:** Introduce a new deterministic, versioned and evaluated recommendation-fusion policy combining model risk, retrieval, generated tests, execution, differential and mutation facts without auto-merging. Preserve earlier policy versions on historical runs; missing/failed mandatory components follow explicit REVIEW/UNKNOWN rules and no LLM/critic can override deterministic HOLD evidence.


## M11 — PyTorch / Hugging Face Semantic Model

### RP-1001 — Semantic training dataset

**Acceptance:** Create a separate versioned text/code-change dataset derived only from allowed pre-outcome data and the frozen split.

### RP-1002 — Model/tokenization selection experiment

**Acceptance:** Benchmark a small appropriate pretrained code/text encoder against simpler embedding baselines before selecting a fine-tuning path.

### RP-1003 — PyTorch training pipeline

**Acceptance:** Implement deterministic seeds where possible, checkpoints, mixed precision only when verified, early stopping, resource metadata, and reproducible config.

### RP-1004 — Held-out evaluation and error analysis

**Acceptance:** Report class/per-repository errors, confidence/calibration, robustness, latency and failure examples on untouched test data.

### RP-1005 — Model card and artifact lineage

**Acceptance:** Document intended use, non-use, data, metrics, bias/limitations, environment, hashes, license, and rollback.

### RP-1006 — Incremental-value ensemble experiment

**Acceptance:** Integrate semantic output only if it adds statistically/practically meaningful held-out value beyond deterministic/XGBoost signals; otherwise keep it optional.


## M12 — Bounded LangGraph Investigation

### RP-1101 — Versioned graph state and node contracts

**Acceptance:** Define typed graph state, immutable evidence refs, node inputs/outputs, termination reasons, and persisted safe summaries.

### RP-1102 — Read-only investigation tools

**Acceptance:** Expose bounded retrieval, feature, graph, test-result and execution-evidence tools; no merge/deploy/write-to-repo authority.

### RP-1103 — Budgets, loops, and cancellation

**Acceptance:** Enforce node/LLM/tool budgets, wall-clock limits, loop detection, cancellation and explicit partial-result behavior.

### RP-1104 — Independent evidence critic

**Acceptance:** Validate claims with deterministic schema, citation-existence, source-entailment and policy checks that do not depend on the generating model. A separate provider/model may add a bounded critic signal but does not count as independent validation by itself and cannot manufacture missing evidence.

### RP-1105 — Human-visible investigation trace

**Acceptance:** Render concise node/result/evidence summaries without storing or exposing hidden chain-of-thought.

### RP-1106 — Agent evaluation

**Acceptance:** Measure task success, groundedness, tool errors, budget usage, latency/cost and compare against the simpler non-agent pipeline.


## M13 — MLflow and Model Governance

### RP-1201 — MLflow tracking deployment

**Acceptance:** Run a pinned local MLflow service with Postgres/object artifact storage or a documented minimal compatible configuration.

### RP-1202 — Dataset/model lineage

**Acceptance:** Log manifest hash, feature schema, code SHA, config, artifacts, metrics and environment for every formal experiment.

### RP-1203 — Prompt/RAG/agent evaluation registry

**Acceptance:** Record versioned evaluation datasets and aggregate results for retrieval, LLM and agent changes without leaking customer code.

### RP-1204 — Model promotion and rollback

**Acceptance:** Define candidate/staging/active lifecycle, approval evidence, compatibility checks, immutable artifacts and rollback.

### RP-1205 — Deployment-outcome feedback

**Acceptance:** Ingest explicitly defined post-deployment outcome signals after a delay/window without overwriting the original prediction evidence.

### RP-1206 — Data quality and drift monitoring

**Acceptance:** Monitor schema/missingness/distribution/performance shifts and require human review before automated retraining/promotion.


## M14 — Security, Reliability, and Observability

### RP-1301 — Security hardening review

**Acceptance:** Threat-model GitHub, tenant isolation, prompt injection, RAG poisoning, model artifacts, SSRF, uploads, runner and admin boundaries; fix ranked critical/high findings.

### RP-1302 — Independent quotas and abuse controls

**Acceptance:** Rate/size/budget limit webhooks, analysis, retrieval, embeddings, LLM, runner and uploads by tenant/user with safe defaults.

### RP-1303 — OpenTelemetry and redacted structured logging

**Acceptance:** Propagate correlation/trace IDs across web/Celery/model/runner paths; prohibit raw source/prompts/secrets and unbounded metric labels.

### RP-1304 — Failure drills

**Acceptance:** Exercise Postgres/Redis/provider/ML model/retrieval/worker/runner failure and prove safe degradation/UNKNOWN rather than false confidence.

### RP-1305 — Retention and deletion

**Acceptance:** Implement tenant-controlled retention/deletion for source snapshots, embeddings, artifacts and analysis with audit and dry-run where destructive.

### RP-1306 — Performance and cost evidence

**Acceptance:** Measure representative latency, queue behavior, model/RAG/LLM/runner cost and publish raw methodology/limitations; no extrapolated capacity claims.


## M15 — Production Packaging and Conditional Model Serving

### RP-1401 — Production images and Docker Compose

**Acceptance:** Create multi-stage non-root images, migration job, health checks, dependency gates and one-command production-shaped local demo.

### RP-1402 — Conditional FastAPI model service

**Acceptance:** Apply the predeclared workload/budget and decision record in docs/20. Extract model inference behind a pinned, authenticated internal FastAPI contract only when at least one recorded memory, startup/latency, GPU scheduling, dependency-isolation or measured scaling criterion is met and the operational/security cost is accepted; otherwise record `KEEP_IN_WORKER` or `DEFER_INSUFFICIENT_EVIDENCE` without scaffolding a service.

### RP-1403 — Optional Ollama local-provider adapter

**Acceptance:** Add a disabled-by-default local LLM adapter only after hosted/fake contracts and privacy tests are stable.

### RP-1404 — Optional vLLM serving

**Acceptance:** Predeclare the docs/20 workload and numeric latency/throughput/memory/cost budgets plus hardware, model-license and privacy requirements. Enable pinned vLLM only when it passes those requirements and materially improves a failing simpler-serving baseline; otherwise record `KEEP_SIMPLE_SERVING` or `DEFER_INSUFFICIENT_EVIDENCE` without scaffolding it.

### RP-1405 — CI/CD and supply-chain gates

**Acceptance:** Add dependency/secret/image scanning, SBOM/provenance where supported, immutable image digests, model/dataset manifest checks and protected promotions.

### RP-1406 — Staging promotion and rollback

**Acceptance:** Promote the same application/model artifacts, run migrations/evals/smoke tests first, and provide compatibility-gated rollback without unsafe DB reversal.


## M16 — Demo and Narrow Pilot

### RP-1501 — One-command fictional demo

**Acceptance:** Seed a licensed fictional repository/history/evidence set and reproduce low/medium/high-risk PR analyses with no paid services required.

### RP-1502 — Recruiter walkthrough

**Acceptance:** Create a concise narrative from PR ingestion through deterministic risk, RAG, AI, sandbox/differential evidence and recommendation.

### RP-1503 — Screenshots and recorded demo

**Acceptance:** Capture reproducible UI evidence from the real stack and label simulated data clearly.

### RP-1504 — Verified portfolio/resume evidence

**Acceptance:** Publish only statements directly proven by code/tests/raw artifacts; explicitly list unproven capacity/customer/revenue claims.

### RP-1505 — Pilot onboarding package

**Acceptance:** Define target engineering team, GitHub permissions, data/privacy choices, exclusions, stop conditions, support and uninstall/data-deletion steps.

### RP-1506 — Pilot measurement plan

**Acceptance:** Measure review time, surfaced actionable risks, false positives, generated-test acceptance, analysis latency/cost and user feedback without claiming causal incident reduction.


## M17 — Final Reviews

### RP-1601 — Final architecture review

**Acceptance:** Review implementation against source docs/ADRs, rank drift, and decide READY_FOR_DEMO / READY_FOR_NARROW_PILOT / NOT_READY.

### RP-1602 — Final security/privacy review

**Acceptance:** Re-run threat model and privacy/data-flow evidence, runner sentinels, dependency scans and least-privilege checks.

### RP-1603 — Final ML/AI/claims audit

**Acceptance:** Audit data provenance/leakage, held-out metrics, calibration, model cards, RAG/LLM/agent evals and every public README/resume claim.
