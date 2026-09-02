# 15 — Security, Privacy and Trust

## Trust boundaries
Browser -> Django; GitHub -> webhook/worker; repo content -> static analysis/RAG; repo content -> hosted LLM only under policy; control plane -> runner; runner -> hostile candidate; worker -> models/providers; tenant A -> shared infra -> tenant B.

## Web security
Secure HttpOnly SameSite session cookies outside dev, CSRF on mutations, role authorization, server-scoped object lookup, strong secret storage, bounded inputs, rate limits.

Tenant isolation does not rely on user-supplied organization/repository IDs or Redis. M2 requires server-derived scope, scoped services/querysets, organization-consistent constraints and cross-context tests for web, Celery, admin and management commands. RLS is optional later defense-in-depth under ADR-017, not a substitute for these controls.

## GitHub
Signature verification, short-lived in-memory installation tokens, least privilege and delivery dedupe. No contents/admin/workflow write permission for the core product; checks/status write is separately requested only when the configured GitHub output adapter requires it.

## Source privacy
Separate metadata/diff/index/execution/LLM-trace/training retention classes. Hosted LLM off unless policy allows. Secret detection/redaction is defense-in-depth, not blanket permission to send source. No shared training on private customer code by default.

## Prompt injection
Repo text is hostile content. It cannot change tenant/tool/sandbox/secret/budget policy. Authorization is server-enforced.

## Sandbox threats
Container escape, fork/resource bombs, mining, network/DNS exfiltration, socket/mount access,
package install scripts, archive traversal/decompression bombs, artifact poisoning and persistence.
M9 addresses only the frozen fictional fixture under ADR-018; arbitrary external repository
execution stays disabled.

Human acceptance of a generated test authorizes review/export only. Execution requires the separate M9 authorization bound to immutable snapshot/proposal/plan hashes and is invalidated by any change.

## Supply chain
Lock deps, vulnerability/secret scans, pinned CI actions in hardened workflows, image scanning, SBOM/provenance later, model artifact checksum verification.

## AI trust
Evidence types are explicit. Confidence is not certainty. Disagreement is shown. Recommendation policy is deterministic/versioned. Do not expose hidden chain-of-thought; store concise structured rationale/evidence references.

## Required tests
IDOR, CSRF/session, webhook tamper, duplicate delivery, prompt injection, cross-tenant retrieval, model mismatch, runner sentinel secret, blocked exfiltration, archive traversal, log redaction.

## M2 security evidence

M2 tests session-only login/logout and CSRF rejection, fail-closed throttle-store outages, role
denial, cross-organization direct-ID denial, non-superuser admin scope and explicit management/
Celery tenant context. Signed fixture webhooks prove tamper rejection, size/event allowlists,
delivery dedupe/conflict, inactive-installation denial and identifier-only task payloads. Both
SQLite and PostgreSQL runs prove cross-organization repository/installation rejection; immutable
record triggers reject raw SQL mutation. This is tenant-boundary evidence, not a claim that the
later live GitHub adapter, full production deployment or hostile-code sandbox is validated.

## M3 static-analysis boundary

Repository source is accepted only as bounded inert UTF-8 text at an exact base SHA. Python source
is parsed with `ast` and is never imported or executed; dynamic imports are findings, not tool calls.
The default worker has no live source-tree provider and safely persists missing graph coverage.
Feature/evidence rows are organization scoped, have composite parent constraints and are append-only
in application and database controls. Optional opaque author keys never leave the history
aggregation path or become identity/employee-scoring features.

## M5 model-artifact boundary

The public synthetic artifact is bounded before JSON parsing and validates root, preprocessing,
individual model and native XGBoost checksums before inference. Exact feature-schema compatibility
is required. Invalid/unavailable learned artifacts cannot replace or erase deterministic evidence;
the current-model read reports explicit baseline fallback. Artifact contents include no customer
source, credentials or provider payloads. Snapshot-risk reads resolve tenant scope server-side and
cross-organization IDs return the safe not-found envelope.

## M6 retrieval boundary

Repository documents are stored and chunked only as bounded inert text. Approval, source identity,
version, checksum, organization/repository scope and retention metadata are mandatory; repository
content cannot select a provider, change tool policy or widen authorization. Every lexical/vector
query applies scope and expiry filters before ranking. Composite database constraints and
cross-tenant tests prevent a chunk/profile/embedding from being rebound to another tenant.

Public model identity, revision, license and safetensors checksum are fixed in source. Real adapters
read only an explicitly provisioned local directory, verify weights before import, disable remote
code and never download on a web/worker request. Provider/model mismatch or outage is visible and
falls back to scoped deterministic evidence. Raw queries/source are not logged or persisted as
retrieval traces in M6; the response retains only a query SHA-256 and cited source/chunk IDs.

## M7 hosted-LLM boundary

The organization-level hosted-LLM kill switch and immutable effective policy are evaluated before
any hosted adapter call. Missing policy, stale terms review, unknown training/retention facts,
unapproved provider/model/content class/region, an unavailable required response-storage control,
oversized context or a cost/token violation denies transmission. Repository overrides must belong to the same organization
and are protected by composite database constraints.

Repository text is encoded inside a versioned data envelope and cannot select providers, change
policy, enable tools, widen budgets or alter authorization. The OpenAI adapter exposes no tools and
does not execute model output. Redaction is bounded and versioned but is not proof that source is
safe to transmit. Persisted evidence excludes prompt/context, provider raw responses, secret values,
hidden reasoning and arbitrary error text; application logging must maintain the same exclusion.
The deterministic fake remains the only enabled-by-default M7 path.

## M8 generated-test boundary

Provider output crosses a strict bounded schema before persistence. Generation metadata must match
the exact completed tenant-scoped M7 evidence, and proposal citations must be a subset of that
evidence's source references. Every lookup begins from the authenticated active organization;
Reviewer role and CSRF protect accept/reject/edit/export. Composite foreign keys and immutable
database triggers prevent cross-tenant rebinding and raw mutation.

The controlled adapter rejects traversal, arbitrary target files, source-file modification,
unexpected commands/imports, dunder introspection and obvious file/process/network capabilities.
Static AST filtering cannot make hostile code safe, so M8 deliberately has no execution path,
repository credential, patch application, runner call or execution approval. Audit metadata keeps
hash/version/lifecycle facts and excludes patch/source content. M9 completed its independent
threat review and isolation signoff before the separate fixture-only execution path became
available.

## M9 sandbox boundary

The signed RP-0801 review is docs/40 and the accepted backend is ADR-018. Durable execution requires
a dedicated rootless Linux Docker host with cgroups v2, default seccomp and enforcing LSM. Plans
cannot request network, mounts, ambient env, alternate image namespace/argv or larger-than-v1
resources. Candidate containers receive no socket/host path/SSH agent/credential, run as numeric
non-root with a read-only root, no capabilities and no-new-privileges, and are force-removed after
each attempt. Live sentinels cover parent secrets, socket/mount, metadata/network, cgroup/tmpfs,
timeout/kill/output and cleanup. These controls reduce risk for the source-controlled fixture and
are not a universal container-isolation claim.

## M10 differential/recommendation controls

M10 adds no execution backend, network path or provider. Signed contracts accept only a finite
checksum-bound synthetic base/candidate/mutation bundle inside the M9 image and preserve the same
no-network/no-mount/non-root/resource controls. Result parsers bound output and reject unknown
schema fields. Explicit masks apply only to two declared nondeterministic display fields and cannot
hide test outcome, HTTP status/schema/body, selected state or selected events.

Differential plans chain to the separate M9 approval and become stale with that source plan.
Composite database constraints prevent tenant/approval/snapshot rebinding. Recommendation inputs
must cite same-tenant persisted evidence; deterministic HOLD has highest precedence, incomplete
mandatory evidence becomes UNKNOWN, and `auto_merge=false` is validated and persisted.
