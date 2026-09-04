# 48 — M12 Owner Learning Note

## 1. Concept implemented

M12 implements a typed LangGraph state machine whose nodes use a fixed read-only tool allowlist,
hard execution/provider budgets, cancellation and loop guards, a deterministic evidence critic,
safe append-only trace persistence and a frozen comparison with the simpler M7 path.

## 2. Why it is used here

A graph makes a multi-stage investigation explicit: collect change/graph evidence, retrieve
history, inspect risk and tests, optionally read execution evidence, criticize the draft, then
compose a human-facing recommendation. Explicit state and transitions make budgets, missing facts,
failures and citations testable. That structure is useful only if it adds value; it does not grant
the model authority or justify replacing a simpler pipeline.

## 3. Algorithm and data assumptions

- Nodes are bounded state transitions, not autonomous actors. A fixed directed acyclic graph avoids
  open-ended planning; a repeated node/state fingerprint is still rejected as a loop.
- Tools read only already authorized immutable evidence references. They do not run code, request
  execution, write repositories, merge or deploy.
- Each factual claim carries citations and machine-checkable fact codes. The critic accepts a claim
  only when every cited ID was returned by a tool and its fact code exists in that cited source.
- The critic independently rechecks deterministic policy. A generated recommendation cannot
  override HOLD/UNKNOWN rules, and same-model self-critique would not count as validation.
- Cancellation, time, step, tool, provider-call, token and cost counters are checked at node
  boundaries. Provider adapters must also enforce their supplied transport timeout.
- The fixture is synthetic and the provider is a local deterministic fake. Perfect fixture scores
  validate contracts, not model intelligence or customer value.
- Because the four-case comparison ties M7 on quality and adds orchestration cost, the graph stays
  optional and disabled by default.

## 4. Key code paths

- `packages/agent_core/contracts.py`: versioned immutable evidence/state/node/result contracts.
- `packages/agent_core/tools.py`: six-method read-only allowlist and per-tool result bounds.
- `packages/agent_core/guards.py`: cancellation, time, step/tool/provider/token/cost and loop guards.
- `packages/agent_core/critic.py`: deterministic citation, structured-entailment and policy checks.
- `packages/agent_core/graph.py`: fixed LangGraph transitions and safe partial-result behavior.
- `adapters/agent/fake.py`: deterministic local-only node provider.
- `apps/web/analysis/agent_investigation.py`: tenant selection, idempotency and safe append-only
  evidence persistence.
- `eng/evaluate_m12_agent.py`: frozen agent/non-agent comparison and guard controls.

## 5. Exact experiment/test to rerun

```text
uv sync --frozen --group dev --group ai --group agent
uv run python -m eng.evaluate_m7_llm --check
uv run python -m eng.evaluate_m12_agent --check
uv run pytest tests/unit/test_agent_core.py tests/integration/test_agent_investigation_persistence.py tests/web/test_agent_investigation.py
```

Inspect comparison task success/groundedness/tool errors, usage totals, latency evidence, every
termination control and `decision.agent_promoted`. Do not enable a hosted provider or default graph
path from these synthetic results.

## 6. Likely interview question and answer

**Question:** Why is your critic independent, and why did you keep LangGraph optional?

**Answer:** The critic uses deterministic schemas, citation membership, exact structured fact codes
and the existing recommendation policy, so it does not ask the generating model to grade itself or
invent missing evidence. The frozen comparison tied the simpler M7 path on task success and
groundedness while adding calls, steps and latency. The right engineering decision was therefore to
retain the bounded graph as an optional experiment, not force complexity into the default path.
