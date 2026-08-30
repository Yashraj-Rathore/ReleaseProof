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
Container escape, fork/resource bombs, mining, network/DNS exfiltration, socket/mount access, package install scripts, archive traversal/decompression bombs, artifact poisoning, persistence. M9 blocks until isolation evidence passes.

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
