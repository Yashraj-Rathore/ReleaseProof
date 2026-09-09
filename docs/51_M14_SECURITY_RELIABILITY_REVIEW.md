# 51 — M14 Security, Reliability, Observability, and Cost Review

## Scope and decision

This is the `RP-1301..RP-1306` completion review dated 2026-09-08. It covers GitHub
ingestion, tenant authorization and database relationships, hostile RAG/LLM input, artifact
references and object deletion, request/upload boundaries, the fixture-only runner, administrative
operations, quotas, telemetry, failure handling, retention, and measurement claims.

**Decision:** M14 may complete with zero open Critical or High findings. M15 remains gated.
External/customer repository execution remains disabled under ADR-018, the deterministic heuristic
remains the active model, and no production capacity or security certification is claimed.

## Ranked findings and remediation

| ID | Initial rank | Boundary and attack | Resolution | Residual rank |
|---|---:|---|---|---:|
| M14-S01 | High | Cost/resource exhaustion had per-request bounds but no independent tenant/user accounting authority. | Added immutable `operational-policy-v1`, PostgreSQL fixed-window counters and idempotent append-only reservations for webhook, analysis, retrieval, embedding, LLM request/token/cost, runner job/CPU and uploads. Tenant and authenticated-user reservations are independent and atomic. | Low |
| M14-S02 | High | Error sites generated unrelated correlation IDs, preventing reliable incident tracing across components. | A server-generated request context now reaches error envelopes/headers; persisted webhook/job correlation reaches Celery; OpenTelemetry instruments Django/Celery and exports bounded trace/metric data. | Low |
| M14-S03 | High | Retention metadata existed, but no tenant-operated audited deletion workflow covered the four required content classes. | Owner/Admin endpoints create exact immutable dry-run or executable plans. Execution rechecks policy/hash, uses a five-minute transaction-local database grant, deletes only planned tenant/public IDs, verifies S3 checksums, reports blocked references, and writes an immutable result/audit. | Low |
| M14-S04 | High | Operational failures were tested piecemeal but not consolidated into a false-SHIP review. | A seven-component failure matrix and regression checks require reject/retain/fallback/failed/UNKNOWN dispositions. Provider, model, retrieval, broker, worker and runner failures cannot synthesize positive evidence. | Low |
| M14-S05 | Medium | Logs could interpolate arbitrary source, prompts, headers, cookies, or exception text. | The production formatter ignores raw messages/extras and emits an allowlist: timestamp, level, bounded logger/event, server correlation/trace, fixed outcome, bounded duration and exception type. Collector processors delete sensitive HTTP/process fields. | Low |
| M14-S06 | Medium | Unbounded metric attributes could expose tenant/source identity and cause cardinality abuse. | Product metrics accept enum component/outcome attributes only. Organization, repository, user, path, prompt, source and artifact identifiers are not labels. | Low |
| M14-S07 | Medium | Artifact deletion could remove the wrong object or leave active lineage inconsistent. | Only the configured S3 bucket is supported; metadata checksum must match object metadata before deletion. Protected/active lineage is reported blocked rather than bypassed. Unsupported artifact schemes remain blocked. | Low |
| M14-S08 | Medium | Uploaded bodies or URL-like values could become memory/SSRF primitives. | Django upload bounds and versioned per-request/upload-count policy fail before persistence. There is no general upload endpoint. GitHub hosts/S3 endpoints remain operator configuration; artifact URIs reject credentials/query/fragment; no user URL fetcher is introduced. | Low |
| M14-S09 | Medium | Local observability/MLflow UIs could be exposed with weak defaults. | Collector, Prometheus, Grafana and MLflow publish on loopback; telemetry images are digest-pinned, capability-dropped, read-only where feasible, and Grafana disables anonymous access/sign-up/analytics plus plugin installation/updates. MLflow remains unauthenticated local-only. | Low |

## Boundary review

### GitHub App and webhook trust

- HMAC and size validation still happen before trusted JSON interpretation. Only allowlisted events
  and actions are accepted, delivery IDs are immutable/idempotent, and tenant identity is derived
  from the server-side installation binding.
- The tenant webhook quota is reserved only after signature/installation resolution. Invalid or
  unknown-tenant floods require an ingress/WAF IP/global limit in a production topology; this is an
  M15 deployment control, not a reason to trust an unverified tenant identifier.
- Installation tokens remain short-lived memory-only values. No token, raw payload, patch, source,
  authorization header, or cookie enters quota, telemetry, or audit records.

### Tenant and administrative isolation

- Operational APIs derive the active organization from the authenticated session and require
  Admin or Owner. The client never supplies an authoritative tenant key.
- Quota, policy, retention-plan, grant, and execution records carry an organization foreign key;
  composite database constraints/triggers prevent cross-tenant parent binding.
- Retention grants are never accepted through an API. They are activated and deactivated inside
  the deletion transaction, expire after five minutes, and allow deletion only from the four
  declared content tables. Other append-only triggers remain rejecting.

### Hostile retrieval and LLM input

- Repository documents remain inert bounded data; code is neither imported nor executed by
  ingestion/chunking. Every query remains organization/repository scoped.
- Prompt text and retrieved content cannot alter routing, evidence allowlists, citations, tool
  permissions, cost limits, recommendation precedence, or runner policy. Invalid structured output
  remains unavailable evidence.
- Hosted transmission still requires an exact tenant policy and reviewed provider/model/content/
  region/training/retention settings. The deterministic fake remains the test/demo default.

### Runner and artifact boundary

- ADR-018 still permits only the source-controlled fictional fixture on the separate rootless
  runner. M14 neither mounts a Docker socket into the app nor enables external repositories.
- Approval consumes tenant and reviewer runner-job/CPU budgets bound to the immutable plan hash.
  Timeout/unavailable/invalid results remain UNKNOWN and never pass.
- Artifact URIs are metadata, not general fetch URLs. Only checksum-matched objects in the configured
  S3 bucket can be erased automatically; referential protection blocks active model lineage.

## Quota defaults and semantics

Exact defaults live in `packages/observability/policy.py` and are policy-versioned. They are safe
starting ceilings, not measured capacity. PostgreSQL is authoritative; Redis may only cache. A
fixed window retains the policy/hash that opened it. An idempotency key consumes once per scope and
quota kind. Multi-resource LLM and runner reservations are atomic.

The application has no generic upload surface. `reserve_upload` atomically applies the size bound
and independent tenant/user request quota and is the mandatory adapter boundary for any future
upload issue; Django additionally refuses bodies above the configured memory limit.

## Retention and deletion semantics

- Classes are `source_snapshot`, `embedding`, `artifact`, and `analysis`.
- A dry-run plan is the default and cannot execute. An executable plan freezes exact candidates,
  cutoffs, organization, policy hash, requester, correlation ID, and a plan checksum.
- Execution expires after seven days and fails if the active retention policy changed. A repeat
  execution returns the immutable prior result.
- At most 1,000 records enter a plan; another plan provides pagination. Foreign-key-protected
  lineage is counted as blocked. It is never force-deleted or mislabeled as erased.
- S3 bytes are checksum-verified and deleted before metadata. Unsupported artifact backends are
  blocked. Backup expiry and provider-side copies remain deployment/operator duties.
- Audit records contain counts and hashes, not deleted content, and intentionally outlive product
  content under a separate security-audit retention obligation.

## Failure drills

| Component | Injected state | Required safe result | Evidence |
|---|---|---|---|
| PostgreSQL | database query unavailable | readiness/request rejection; no durable-accept claim | `tests/web/test_health.py` |
| Redis/outbox | publisher failure | PostgreSQL job/outbox retained for bounded retry | `tests/integration/test_github_webhook_ingestion.py` |
| LLM provider | explicit unavailable error | missing LLM evidence; deterministic evidence preserved | `tests/integration/test_llm_evidence_persistence.py` |
| Learned model | absent/checksum-invalid artifact | deterministic baseline or UNKNOWN | `tests/unit/test_classical_ml.py`, risk web tests |
| Retrieval | semantic/reranker failure | lexical evidence or explicit unavailable status | `tests/integration/test_retrieval_persistence.py` |
| Celery worker | missing/invalid job input | bounded failed/not-found state, never success | ingestion integration tests |
| Runner | unavailable/timeout/invalid result | UNKNOWN, never SHIP | differential/recommendation tests |

The frozen consolidated matrix and measured evidence are in
`artifacts/evaluation/m14_operations_eval_v1.json`; `python -m eng.evaluate_m14_operations --check`
rejects an incomplete matrix, false-SHIP allowance, unsupported validation claim, or invalid hash.

## Observability deployment

- Python pins: OpenTelemetry API/SDK/OTLP HTTP `1.44.0`; Django/Celery instrumentation `0.65b0`.
- Local images: Collector Contrib `0.159.0`, Prometheus `3.14.0`, Grafana `13.2.1`, all by digest.
- The collector accepts OTLP/HTTP, exports bounded application metrics to Prometheus, emits basic
  trace diagnostics locally, deletes sensitive HTTP/process trace attributes, batches, and limits
  memory. Application metric attributes are already a closed enum set.
- Prometheus retains at most seven days/512 MB locally. Grafana has a non-editable Prometheus
  datasource, no anonymous access and no plugin installation/automatic updates. CI sends a bounded
  metric/span and queries the series.
- Application logs remain structured stdout; M14 adds no log backend or raw messages to traces.

## Performance and cost evidence

The M14 artifact records 20 wall-clock repetitions of a sequential synthetic in-process control-
plane work sample and a 1,000-message deterministic publisher burst, using nearest-rank p95. It
also checksum-links M6–M13 component evidence. The raw environment, method, values, cost status,
and limitations are in the artifact.

This is not a customer, database, Celery/Redis, hosted-provider, or live-sandbox benchmark. The
local deterministic path incurred zero external billed cost. Hosted LLM, external runner, and
production infrastructure cost remain **not yet measured**. Capacity, customer latency, production
runner latency, and hosted-provider latency remain **not validated**.

## Residual risks accepted for M14

- Production edge/global/IP controls, authenticated production dashboards, log aggregation,
  alerts/SLO routing, backup lifecycle verification, and real queue/load tests depend on M15.
- Provider-side copies/backups require provider-specific contracts; results report only confirmed
  local actions.
- Container controls and known fixture sentinels are not proof against every kernel/runtime escape.
  External hostile code remains disabled.
- The 1,000-candidate plan bound requires repeated plans for large tenants and intentionally favors
  reviewability over bulk deletion speed.

None permits a security, privacy, performance, capacity, cost, or customer-outcome claim.
