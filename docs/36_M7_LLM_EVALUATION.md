# 36 — M7 LLM Evaluation

## Decision

M7 validates the evidence-grounded LLM contract, privacy gate, strict parser, safe persistence and
deterministic provider path. The deterministic fake remains the default. No hosted provider was
called, so this report does not promote or claim the usefulness, latency, cost, retention or
regional behavior of the OpenAI configuration.

## Frozen configuration

| Item | Exact identity |
|---|---|
| Evaluation schema | `m7-llm-eval-v1` |
| Fixture | `tests/fixtures/llm/m7_grounding_v1.json` |
| Fixture license | `CC0-1.0`; explicitly synthetic |
| Fixture SHA-256 | `e7a3a35c38e5fae9fc9f7c76be4136a8fcaa6eb76ef45f265cdc2a96682a213a` |
| Prompt | `change-analysis-prompt-v1` |
| Prompt SHA-256 | `de5399fe7640da726411cfcd0dadad0e5e58b6423202590458e35a95a82a0374` |
| Output schema | `analysis-suggestion-v1` |
| Schema SHA-256 | `9fcf0e4be678643081726e579e2ed6df5ac17a45c5598c0c6c23ea0151a5f296` |
| Evaluated provider | `deterministic_fake` |
| Evaluated model | `deterministic-evidence-synthesizer-v1` |
| Artifact | `artifacts/evaluation/m7_llm_eval_v1.json` |
| Artifact root SHA-256 | `5e4f7abc185842fc914b58872ca42971bef4641d6cc81d04ab7dce6564c3eca4` |

The six cases contain four valid structured suggestions and two negative controls: an unknown
citation and an authority-like extra field. Valid cases exercise grounded migration evidence,
empty insufficient evidence, hostile prompt-injection text and conflicting evidence. Suggested
check usefulness uses exact source-controlled gold values rather than model self-grading.

## Measurements

| Metric | Result | Denominator/meaning |
|---|---:|---|
| Schema validity | `1.0` | 4/4 valid cases accepted |
| Negative-control rejection | `1.0` | 2/2 invalid cases rejected |
| Citation support | `1.0` | 5/5 evidence-bearing claims use allowed IDs |
| Unsupported-claim rate | `0.0` | 0/5 evidence-bearing claims unsupported |
| Suggested-check exact match | `1.0` | 3/3 cases with a gold requested check |
| Prompt-injection resilience | `1.0` | 1/1 hostile-text case stays within its fixed suggestion |
| Stability | `1.0` | every valid result identical over five repeats |
| Fake input usage | `3401` | conservative byte-count proxy, not provider-token billing |
| Fake output usage | `2481` | conservative byte-count proxy, not provider-token billing |
| Cost | `0` micro-USD | deterministic fake only |

One hundred local full-fixture repetitions on CPython 3.13.15/Windows recorded median `1.8031 ms`,
p95 `3.2425 ms` and minimum `1.4835 ms`. These timings cover only in-process fake-provider parsing
and evaluation. They exclude Django persistence, PostgreSQL, queues, provider/network latency and
real model inference and must not be used as a product latency claim.

## Failure and security evidence

- Strict parsing rejects duplicate/unknown keys, malformed types, invalid enums, over-bound values,
  non-finite values and evidence IDs outside the request context.
- Provider timeout/retry, cancellation and token/cost bounds are explicit. The OpenAI SDK's built-in
  retries are disabled so one bounded policy controls retry behavior.
- Hosted routing denies missing/incompatible policy and does not call the provider. Local-only
  routing cannot use a hosted provider. Redaction is versioned defense-in-depth, not permission.
- Tenant scope is resolved server-side. Composite constraints reject policy/repository mismatch;
  cross-tenant context IDs are denied before provider use.
- Successful and failed evidence rows exclude source/prompt text, raw provider responses, hidden
  reasoning, credentials and arbitrary exception strings. Existing deterministic evidence remains.

## Reproduce

```text
uv sync --frozen --group dev --group ml --group ai
uv run python -m eng.evaluate_m7_llm --check
uv run pytest tests/unit/test_llm_core.py tests/unit/test_openai_adapter.py
uv run pytest tests/integration/test_llm_evidence_persistence.py
```

## Limitations and next gate

All evidence and outputs are synthetic. No customer/public source was transmitted; no model weights
were downloaded; no paid API was called. Before hosted activation, an organization must approve
current contractual training/retention/region/storage facts and versioned pricing, and a separately
authorized evaluation must measure usefulness, failure behavior, real latency and billed cost on
appropriately licensed data. M8 may consume only these strict suggestions to create reviewable test
proposals; M7 itself does not write files or execute tests.
