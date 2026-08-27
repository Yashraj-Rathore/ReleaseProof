# 04 — API and Contracts

## Browser/API model
Primary UI is same-origin Django + HTMX. DRF supplies structured APIs and integrations. Internal model/runner contracts are separately versioned.

## Safe error envelope
```json
{"error":{"code":"stable_code","message":"safe message","correlation_id":"opaque","details":{}}}
```
Never return stack traces, secrets, raw provider payloads, or arbitrary source.

## Representative routes
- `GET /health/live`, `/health/ready`
- `GET /app/repositories/`
- `GET /app/repositories/{id}/pulls/{number}/`
- `GET /api/v1/me`
- `GET /api/v1/analyses/{id}`
- `GET /api/v1/analyses/{id}/evidence`
- `POST /api/v1/repositories/{id}/reanalyze`
- `POST /api/v1/analyses/{id}/generated-tests/{proposal}/accept|reject`
- `POST /api/v1/execution-plans/{id}/approve` (M9+, separate execution authorization)
- `GET /api/v1/models/current`
- `GET /api/v1/evaluations/latest`
Mutations require session + CSRF + role checks.

## GitHub webhook
`POST /webhooks/github`: bounded raw body -> signature verify -> event/action allowlist -> delivery dedupe -> server-resolved installation/org -> atomically commit durable receipt/job/outbox -> relay to Celery. A broker outage leaves committed work pending for recovery rather than returning a false accepted-without-work state.

## Analysis contracts
`AnalysisRequestV1`: snapshot, requested components, policy snapshot/version, reason.
`AnalysisResultV1`: run/snapshot/base/head, component outcomes, recommendation, evidence IDs, producer/schema versions.

## Risk model contract
`RiskModelRequestV1`: exact feature-schema version + normalized feature payload.
`RiskModelResponseV1`: exact model artifact/checksum, raw score, calibrated probability nullable, band, explanation, latency metadata.
Feature mismatch is rejected.

## Retrieval contract
Server-resolved org/repo scope, query, filters, max candidates. Results include document/chunk source/version, lexical/vector/fusion/rerank scores and safe excerpt.

## LLM schema
Strict versioned object: concise summary, risk hypotheses, allowed evidence IDs, suggested checks/tests, missing information, uncertainty. Unknown evidence ID => invalid output.

## Runner contract
Runner accepts only immutable/signed internal `ExecutionPlanV1`: artifact hashes, image/toolchain, allowlisted commands, resource/network policy, timeout/output limits. No free-form host paths or Docker options.

Runner returns plan hash, image digests, command outcomes, timings/resource observations, bounded artifact refs, explicit timeout/killed/isolation failure.

## Idempotency/staleness
GitHub delivery + snapshot identity dedupe. Manual reanalysis may use idempotency key. Old-head analysis cannot publish current-head conclusion.

Proposal acceptance and execution approval are distinct. Accepting/editing/exporting a generated test never enqueues execution. Editing or head movement invalidates prior execution approval; an approved execution request names the exact proposal revision, snapshot and execution-plan hash.
