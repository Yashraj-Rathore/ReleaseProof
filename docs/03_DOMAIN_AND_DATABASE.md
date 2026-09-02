# 03 — Domain and Database

## Tenancy
All customer records belong to `Organization`. Repository identity is tied to GitHub numeric IDs/installations, not user-entered names. M2 tenant isolation is enforced by server-derived organization context, organization-scoped application services/querysets, object-level authorization and composite database constraints. Raw unscoped ORM access is prohibited outside audited repository/adaptor code.

PostgreSQL row-level security is not an assumed MVP control: pooled web/Celery connections require a proven transaction-scoped tenant-context design before RLS can be trusted. ADR-017 requires the application and constraint controls to stand alone; a later RLS defense-in-depth change needs its own ADR and cross-context tests.

## Key entities

### Organization / Membership
Organization stores lifecycle, hosted-LLM policy, org-learning policy, retention and budgets. Membership role: Owner/Admin/Reviewer/Member/ReadOnly.

### GitHubInstallation
Organization, GitHub installation/account IDs, permissions snapshot, lifecycle. **Never persist short-lived installation access tokens.**

### Repository
Organization, GitHub repository ID, display owner/name, default branch, language metadata, analysis/index/execution policy.

### PullRequestSnapshot
Immutable repository/PR/base SHA/head SHA/event identity/title/body metadata, changed files, diff artifact/hash, schema version.

### ChangeFeatureSet
Snapshot, feature-schema version, deterministic values, extractor version, graph artifact/hash. Must be recomputable.

### AnalysisRun
Snapshot, requested components/policy snapshot, lifecycle, timestamps, correlation ID, recommendation + recommendation-policy version.

### AsyncJob / OutboxEvent
Authoritative job/idempotency key, owning organization/run, requested task type/version, bounded attempt state, availability time and terminal outcome; transactional outbox topic/payload version/published state. The outbox contains identifiers, not raw source. Redis/Celery result state is never authoritative.

### EvidenceItem
Append-only: kind (`deterministic`, `ml`, `retrieval`, `llm`, `test`, `execution`, `security`, `unknown`), severity/confidence vocabulary, title, structured payload, source refs, producer/version.

### RiskScore
Analysis, model/baseline artifact, feature version, raw score, calibrated probability nullable, band, threshold policy, explanation.

### KnowledgeDocument / KnowledgeChunk / KnowledgeEmbedding
Document/chunk: org/repo, source type/id/version/hash, content metadata, versioned normalized text, `simple`-configuration FTS vector, ACL/scope. Embedding: chunk, exact embedding-version/model/revision/dimension, vector and lifecycle. Each dimension/model version uses a compatible physical vector index and is built beside, not over, the active version.

### DatasetManifest
Version/hash, provenance, extraction/label rules, feature version, split rule, counts/class balance/unknowns, usage/license notes, synthetic flag.

### ModelArtifact
MLflow/model identifier, algorithm, dataset manifest, feature version, metrics summary, lifecycle (`candidate/approved/retired`), checksum.

### PromptVersion / EvaluationSuite
Immutable/versioned prompts and frozen evaluation cases.

### GeneratedTestProposal
Analysis, immutable revision/hash, adapter, file/content artifact, rationale/evidence refs and M8
lifecycle (`draft`, `accepted_for_export`, `rejected`, `superseded`). Editing creates a new draft
revision. M8 acceptance permits export only. M9 adds separate immutable `ExecutionPlan`,
`ExecutionApproval` and `ExecutionRun` records bound to the current snapshot, proposal hash,
execution-plan hash and approving Reviewer/Admin; `execution_approved` and `executed` are not M8
proposal states.

### ExecutionPlan / ExecutionApproval / ExecutionRun / Observation
The M9 plan stores exact fixture/check-out/proposal/input/image identifiers, argv, constant
environment, empty mounts, network `none`, quotas, artifacts and plan hash. Approval separately
repeats the exact snapshot/proposal/plan hashes. Runs are append-only and idempotent; they retain
runner/image/plan identity, outcome, timing, bounded output hashes/excerpts, isolation checks,
timeout/kill, cleanup and stale-at-recording state.

### DifferentialPlan / DifferentialRun / RecommendationDecision
The M10 plan is immutable and points to one exact M9 plan and its separate human approval. It binds
controlled base/candidate revision checksums, the same image/environment/resource/workload policy,
the nondeterminism-mask version and bounded mutation set. The result stores comparable test/probe/
HTTP/state/event facts, bounded output, mutation outcomes and limitations. A recommendation row
binds the snapshot, differential run, exact fusion-policy version, input hash and decision hash;
historical decisions are never rewritten when a later policy is introduced.

### DeploymentOutcome
Optional feedback taxonomy (`no_issue`, `revert`, `hotfix`, `incident`, `manual_label`, `unknown`), source/confidence/observation window and org-training eligibility.

### AuditLog
Append-only actor/org/action/resource/correlation and safe metadata. Never raw source/secrets.

## Persistence rules
- Opaque public IDs.
- Unique webhook delivery IDs.
- Unique immutable snapshot identity.
- Optimistic versioning on mutable policy.
- Vector/FTS queries always include org/repo scope.
- Tenant-owned parent/child relationships use organization-consistent composite foreign keys such as `(organization_id, parent_id)` backed by a matching unique key. Any schema-level exception requires a documented migration rationale plus fail-closed service and cross-tenant tests; services always verify scope before lookup or mutation.
- Embedding model/dimension changes create new index version.
- Historical evidence never silently rewritten when model/prompt changes.

### M2 implemented enforcement

- Browser scope comes from an authenticated active membership stored in the server-side session;
  verified GitHub installation IDs derive webhook scope. Payload organization IDs are ignored.
- Scoped querysets/application services cover HTTP, Celery, admin and management-command entry
  points. Non-superuser admin querysets are membership scoped; the outbox command requires one
  explicit organization public UUID.
- Database composite foreign keys enforce organization consistency for repository/installation,
  receipt/installation, snapshot/repository, snapshot/receipt, job/snapshot and outbox/job pairs.
  PostgreSQL constraints and SQLite test triggers both reject mismatches immediately.
- Webhook receipts, pull-request snapshots and audit records reject update/delete in application
  paths and through database triggers. Mutable job/outbox lifecycle state remains bounded and
  separately versioned.
- Installation records persist an approved credential reference only. Installation access tokens
  have a redacted, bounded process-memory cache contract and no model/cache/task serialization.

### M3 implemented change evidence

- `PullRequestSnapshot` schema `github-pr-snapshot-v2` may retain a bounded opaque provider author
  key and commit count. The author key is used only to derive aggregate repository familiarity; it
  is never emitted as a feature or evidence value.
- `ChangeFeatureSet` is append-only and uniquely identifies snapshot + feature-schema + extractor
  version. It persists normalized diff, feature values/missingness/provenance, inline bounded graph,
  blast-radius and pre-change history artifacts plus their stable SHA-256 hashes.
- `EvidenceItem` persists ordered, append-only deterministic risk factors with rule/schema/producer
  versions and bounded source references. M3 records no score, threshold, band or recommendation.
- Organization/snapshot/feature-set relationships have composite database foreign keys. A separate
  `(feature_set_id, snapshot_id)` constraint prevents evidence from citing a different same-tenant
  snapshot. SQLite test triggers mirror the PostgreSQL constraints and append-only triggers.

### M4 implemented dataset and baseline evidence

- The canonical synthetic dataset is a source-controlled manifest/artifact rather than tenant
  product state. It records the admitted source, license/terms evidence, immutable source and split
  hashes, extraction-code commit, label/feature/split versions, exclusions, counts, leakage report
  and limitations.
- `RiskScore` is append-only and tenant-bound to the exact snapshot and `ChangeFeatureSet`. It names
  the baseline artifact/hash, feature schema, threshold policy, raw score/band, rule contributions,
  missing requirements and result hash. Deterministic rows require `calibrated_probability=NULL`.
- Composite database constraints independently enforce organization/snapshot/feature-set identity,
  including a same-snapshot constraint. PostgreSQL and SQLite both reject raw updates/deletes.

### M5 implemented learned-model evidence

- The small committed `classical-risk-artifact-v1` JSON binds the unchanged synthetic dataset and
  split hashes, training-code commit, exact runtime, train-only preprocessing, logistic/XGBoost
  parameters, raw test predictions/metrics, calibration failure, rollback and root/model checksums.
  It is source-controlled fixture evidence rather than a tenant/customer database record.
- `RiskScore` continues to persist only the active deterministic artifact because neither learned
  candidate passed promotion. Public risk reads resolve the snapshot inside the active organization
  and then select the exact active artifact/hash; no user-supplied organization ID controls scope.
- A future approved learned artifact may reuse the append-only `RiskScore` contract only after its
  probability/score validation and lifecycle rules are implemented by an assigned promotion issue.

## Retention
Separate policies for metadata, raw diff/source index, execution logs, LLM traces, datasets and training eligibility. Org deletion removes active access promptly and schedules documented tenant-scoped deletion. Private-data-derived artifacts follow the same policy.

### M6 implemented retrieval evidence

- `KnowledgeDocument` and `KnowledgeChunk` are append-only organization/repository-bound records.
  They retain approved source type/identity/version/URI, content and chunk hashes, line/heading
  provenance, exact chunk/normalizer versions and an organization-policy-derived retention date.
- `LexicalIndexProfile` and `KnowledgeLexicalIndex` build versioned PostgreSQL `simple` FTS rows
  beside existing profiles. The active-profile switch changes only profile lifecycle metadata; it
  never rewrites source chunks or historical lexical rows.
- `EmbeddingIndexProfile` records exact model ID, revision, safetensors checksum, license,
  dimension, adapter, chunk version and physical table/index. `KnowledgeEmbedding384` is the M6
  dimension-compatible pgvector table with a cosine HNSW index. A different dimension requires a
  new physical table/migration rather than guessing or coercing values.
- PostgreSQL composite foreign keys and equivalent SQLite test triggers independently enforce
  organization/repository/document/chunk/profile consistency. Document, chunk, lexical and vector
  rows reject application and raw-SQL update/delete before the governed M14 retention path.
- Retrieval selects only unexpired rows from one active lexical and embedding profile inside the
  server-provided organization/repository scope. Reranker/provider failure leaves attributable
  lexical/hybrid evidence instead of fabricating a historical claim.

### M7 implemented LLM policy and evidence

- `HostedLLMPolicy` is an immutable, versioned organization default or repository override. It
  records route, provider/model/content allowlists, byte/token/cost limits, redaction version,
  training-use and terms-review facts, retention duration, approved regions, provider storage
  behavior, approver role and timeout/retry bounds. The newest repository override wins, then the
  newest organization default; absence or incompatible facts fail closed.
- Composite `(organization_id, repository_id)` enforcement prevents a policy from naming another
  tenant's repository. PostgreSQL and SQLite triggers reject raw updates/deletes, while a new
  version is required for every policy change.
- Each attempted analysis appends or reuses one tenant/snapshot/feature-bound `EvidenceItem` of
  kind `llm`. Successful rows contain only the strict suggestion, cited evidence IDs, safe policy
  decision/hash, exact prompt/schema/model/adapter/SDK identities, usage and elapsed time. Denied or
  failed rows contain a stable status/reason and preserve pre-existing deterministic evidence.
- Prompt input, retrieved source, provider raw output, credentials, arbitrary provider errors and
  hidden reasoning are not persisted in the LLM evidence payload. Idempotency binds the immutable
  context, policy, provider and versioned request configuration.

### M8 implemented generated-test proposals

- `GeneratedTestProposal` stores one immutable `generated-test-proposal-v1` revision with its exact
  content hash, controlled adapter/version, source M7 LLM evidence, citations, inert patch,
  proposed command, generation identity and static-validation report.
- `ProposalLifecycleEvent` is append-only. The initial event creates `draft`; Reviewer actions may
  add `accepted_for_export` or `rejected`, while a content edit creates a new draft and appends
  `superseded` to the prior revision. Duplicate transitions are idempotent.
- Composite organization/source, organization/parent and organization/proposal constraints reject
  cross-tenant binding. PostgreSQL constraints/triggers and SQLite test triggers also reject raw
  proposal/event update/delete, invalid lifecycle chains and acceptance of a statically invalid
  proposal.
- Export returns only the already accepted bounded patch and appends a safe audit record. No M8
  model or service references an execution plan, execution approval, runner job or repository
  write, and no analysis job/outbox event is created by review/export.

## M9 execution evidence implementation

- Plan, approval and result rows are tenant-bound with composite database foreign keys/test
  triggers and immutable at both application and database layers.
- Plan creation is idempotent by organization/hash and neither approves nor enqueues execution.
  Reviewer approval is separately CSRF/role gated and fails when the head/proposal is stale.
- Result ingestion requires a valid signature and exact plan/image/attempt binding. Duplicate
  identical requests reuse evidence; conflicting duplicates fail closed. A late result is retained
  with `stale_at_recording=true`, never promoted as current.
- Audits store only opaque IDs, hashes, outcome, attempt and staleness—not patches, source, secrets
  or output excerpts.

## M10 differential and recommendation evidence implementation

- `DifferentialPlan` is one-to-one with the source execution plan and repeats its exact approval,
  tenant, snapshot, proposal/input hash and image bindings through the strict payload.
- `DifferentialRun` is append-only/idempotent by tenant key and plan attempt. It records the strict
  result hash, outcome, killed/eligible mutation counts and whether the source plan was stale when
  evidence arrived.
- `RecommendationDecision` is append-only per differential run and policy version. Its payload is
  reconstructed and re-evaluated during validation; advisory-only and `auto_merge=false` are
  invariants, not UI conventions.
- Composite foreign keys/triggers reject cross-tenant plan, approval, run and snapshot rebinding.
  Database triggers reject raw update/delete of all three M10 record types.
