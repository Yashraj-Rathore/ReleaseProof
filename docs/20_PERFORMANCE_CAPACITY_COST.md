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
