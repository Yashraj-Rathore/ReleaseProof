# 18 — Observability and Operations

## Correlation
Propagate server-generated correlation/trace IDs from webhook -> snapshot -> Celery -> retrieval/model/LLM -> execution plan -> runner result.

## Logs
Safe structured fields: time/severity/service/correlation/trace/opaque org-analysis IDs/component/outcome/latency. Never log secrets, source/diffs, auth headers/cookies, prompt bodies/customer docs by default.

## Metrics
Webhook accept/reject/dedupe, analysis queue/completion/failure/stale, component latency/error, retrieval/rerank latency, model inference, LLM requests/tokens/cost estimate/failure, sandbox queue/run/timeout/kill, recommendation distribution, queue depth. Avoid high-cardinality file paths/source in labels.

## Tracing
OpenTelemetry internally. Hosted/provider/MLflow trace content follows privacy policy.

## Health
`/health/live`: process.
`/health/ready`: essential dependencies for that role. Optional LLM outage must not necessarily make web unready if graceful degradation is supported.

M13's local MLflow container has separate `/health` and exact `/version` checks. Its tracking
metadata is in PostgreSQL and artifacts are proxied to SeaweedFS. CI bootstraps the bucket before
writing governance artifacts and then runs an idempotent registration smoke. The local service is
optional to core web readiness: an unavailable tracker must fail experiment registration visibly
without erasing already committed evaluation or deterministic risk evidence. Do not emit run IDs,
model tags or drift feature names as unbounded production metric labels.

## Controls
Global/org analysis pause, hosted LLM kill switch, sandbox kill switch, model rollback, stale-run cancellation, retention jobs.

## Alerts
Actionable symptoms only: webhook rejection surge, queue age, error ratio, model load failure, runner isolation failure, persistent provider outage, DB saturation.
