# 20 — Performance, Capacity and Cost

## Principle
Targets are hypotheses until measured; every published number includes environment and raw artifact.

Track separately: webhook durable acceptance, deterministic extraction, retrieval, classical inference, semantic inference, hosted LLM, full agent, sandbox queue/run, dashboard latency.

## Initial design targets — not claims
Webhook acceptance should stay quick; deterministic fixture extraction seconds not minutes; classical inference comfortably sub-second; local retrieval interactive; sandbox asynchronous.

## Budgets
Per-org hosted LLM calls/tokens/cost, embeddings, sandbox CPU-minutes/concurrency, optional GPU quota, artifact retention.

## Method
Fixed fixtures, warm/cold distinction, repetitions, percentile only when sample supports it, controlled hardware for meaningful claims, raw JSON/CSV, regression threshold based on baseline variance.

## Conditional model-serving decision gate

Before profiling, RP-1402 records the representative workload/environment and numeric budget for worker resident memory, cold start, steady-state latency/throughput and queue delay. FastAPI extraction is permitted only when evidence shows at least one of: duplicated worker model memory violates the recorded budget; startup or inference violates its recorded budget and an independent process addresses it; GPU scheduling/batching requires a distinct runtime; incompatible model/application dependencies cannot coexist in the locked worker environment; or independently scaling inference has a measured capacity/cost benefit. The decision record compares the in-worker baseline, includes operational/security cost and selects one outcome: `KEEP_IN_WORKER`, `EXTRACT_FASTAPI`, or `DEFER_INSUFFICIENT_EVIDENCE`.

Ollama/vLLM use the same predeclared-budget method and additionally require compatible hardware and model-license/privacy review. Measurements are evidence for the recorded environment, not universal capacity claims.

## M14 measurement evidence

`m14-operations-evaluation-v1` records the raw local environment, 20 repetitions, minimum/median/
nearest-rank-p95 for a sequential synthetic control-plane work sample, and a 1,000-message in-memory
publisher burst. It checksum-links prior model/RAG/LLM/runner/agent evaluation artifacts rather
than silently combining figures measured under different methods.

The measured pipeline excludes PostgreSQL, Redis/Celery, network, a paid provider, and live sandbox
execution. The queue measure excludes broker scheduling and worker saturation. These figures are
development regression evidence only. Local fake external billed cost is $0; hosted LLM, external
runner and production infrastructure cost are not yet measured. No capacity, customer-latency,
hosted-provider-latency or production-runner-latency claim is made. See the raw artifact and docs/51.
