# 37 — M7 Owner Learning Note

## 1. Concept implemented

M7 implements evidence-grounded advisory LLM analysis: a provider-neutral typed contract, strict
versioned JSON Schema, deterministic fake, one pinned OpenAI Responses adapter, immutable privacy
routing, safe append-only evidence and a frozen deterministic evaluation.

## 2. Why ReleaseProof uses it

Deterministic features, risk scores and retrieved history are useful but fragmented. The LLM layer
may synthesize those facts into reviewer-friendly risks, uncertain hypotheses and proposed checks.
It remains advisory: it cannot change tenant scope, deterministic recommendation, tool policy,
sandbox permissions or evidence already recorded.

## 3. Algorithm and data assumptions

- Every evidence-bearing claim must cite an ID in the server-built request context.
- A strict schema catches structural and citation errors; it does not prove a claim is semantically
  true, so unsupported-claim evaluation and human review still matter.
- Repository content is hostile data, never trusted instructions. Privacy policy is evaluated
  outside the model before transmission.
- Redaction can miss secrets and is only defense-in-depth. Hosted routing additionally requires
  explicit contractual training, retention, region and storage facts.
- The frozen fixture is synthetic. Perfect fake-provider metrics validate code paths, not hosted
  model quality or customer outcomes.

## 4. Key code paths

- `packages/ai_core/contracts.py`: request/response/error and suggestion types.
- `packages/ai_core/schema.py`: strict parser and evidence-reference validation.
- `packages/ai_core/prompting.py`, `prompts/`, `schemas/`: versioned content and hashes.
- `packages/ai_core/policy.py`: fail-closed route decision and redaction.
- `adapters/llm/fake.py`: deterministic, network-free provider.
- `adapters/llm/openai_responses.py`: exact hosted request, budgets, timeouts and retry behavior.
- `apps/web/organizations/models.py`: immutable hosted policy.
- `apps/web/analysis/llm_evidence.py`: tenant-scoped context, routing and safe evidence append.
- `eng/evaluate_m7_llm.py`: frozen deterministic evaluation and artifact verification.

## 5. Exact experiment and tests to rerun

```text
uv run python -m eng.evaluate_m7_llm --check
uv run pytest tests/unit/test_llm_core.py tests/unit/test_openai_adapter.py tests/unit/test_provider_fakes.py
uv run pytest tests/integration/test_llm_evidence_persistence.py
uv run python eng/validate.py
```

The evaluation artifact must keep root hash
`5e4f7abc185842fc914b58872ca42971bef4641d6cc81d04ab7dce6564c3eca4` unless the reviewed fixture,
prompt, schema or evaluator intentionally changes and the report is regenerated.

## 6. Likely interview question

**Question:** Why is strict structured output plus citations still not enough to trust an LLM?

**Answer:** Schema validation proves shape, allowed vocabulary and citation membership, not that the
cited evidence entails the statement. ReleaseProof therefore keeps deterministic evidence
authoritative, measures citation support and unsupported claims on frozen cases, shows uncertainty,
rejects invalid outputs and requires a human reviewer. Privacy and tenant policy are enforced before
the model call and never delegated to the model.
