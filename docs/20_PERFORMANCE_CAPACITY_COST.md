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

## M15 conditional-serving decision record

Before reviewing M14 evidence, M15 fixes this representative workload and budget for each optional
serving comparison: one bounded pull-request feature record, two application-worker replicas, CPU
by default, no downloaded model and no external repository execution. The numeric hypotheses are:

| Dimension | Budget |
|---|---:|
| resident model memory per worker | 768 MiB maximum |
| cold model/process start | 10,000 ms maximum |
| steady-state inference p95 | 250 ms maximum |
| steady-state throughput | 4 records/second minimum |
| broker queue-delay p95 | 2,000 ms maximum |
| incremental serving infrastructure | USD 75/month maximum |

These are extraction-decision budgets, not achieved production SLOs. A controlled environment,
fixed fixture, warm/cold separation and sufficient repetitions are still required before a measured
value can be compared to them.

The RP-1402 decision is `DEFER_INSUFFICIENT_EVIDENCE`. The active risk artifact is the
framework-light deterministic heuristic, not a resident learned model. M14 measured only a
sequential in-process synthetic control-plane p95 and explicitly did not measure worker resident
model memory, worker cold start, Redis/Celery queue delay, worker saturation or independent
inference scaling/cost. No extraction criterion is demonstrated, and the additional authenticated
service/trust boundary has not been operationally accepted. No FastAPI package or service is added.

RP-1403 Ollama is `DEFER_INSUFFICIENT_EVIDENCE`: fake/hosted contracts exist, but there is no
approved organization-local privacy demand, hardware profile, immutable local model/license review
or grounding/schema evaluation. RP-1404 vLLM is also `DEFER_INSUFFICIENT_EVIDENCE`: there is no
failing simpler-serving baseline, approved GPU, selected licensed model, privacy review, or measured
throughput/cost advantage. Neither adapter/service is scaffolded. The exact machine-readable record
is `artifacts/evaluation/m15_release_eval_v1.json`; it must be updated before revisiting any decision.
