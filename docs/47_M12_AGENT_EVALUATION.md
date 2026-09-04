# 47 — M12 Bounded Agent Evaluation

## Scope and identity

- Evaluation schema: `m12-agent-eval-v1`
- Graph/state: `bounded-investigation-graph-v1` / `agent-state-v1`
- Agent provider: local `deterministic-agent-node-v1`
- Independent critic: deterministic structured schema/citation/fact/policy checks
- Comparison: M7 `deterministic-evidence-synthesizer-v1` plus the same
  `recommendation-fusion-v1`
- Fixture: `tests/fixtures/agents/m12_investigation_v1.json`, seven synthetic CC0-1.0 cases
- Artifact: `artifacts/evaluation/m12_agent_eval_v1.json`, root SHA-256
  `2b3dd96716539d884e5edab6a2f3624bf3909801d0acc6382b3f3ec44427f782`

No customer code, public repository, paid/hosted provider, model download or sandbox execution was
used. The fixture's expected decisions are deterministic contract assertions, not production
labels or customer outcomes.

## Predeclared comparison

The four shared cases cover SHIP, deterministic HOLD, missing-evidence UNKNOWN and mutation-driven
REVIEW. Task success requires the exact expected deterministic recommendation and clean critic/
schema result. Groundedness counts factual claims whose citations exist and whose structured fact
codes occur in the cited tool result. Tool error rate is recorded separately. Calls, steps,
input/output tokens and integer micro-USD cost are raw fake-provider counters.

The agent promotion condition requires a task-success or groundedness improvement without worse
tool-error rate. Equality is not improvement. This intentionally prevents orchestration complexity
from being promoted merely because it exists.

## Frozen synthetic results

| Metric | M12 graph | M7 non-agent |
|---|---:|---:|
| Shared cases | 4 | 4 |
| Task success | 1.0 | 1.0 |
| Citation/fact groundedness | 1.0 (20/20) | 1.0 (8/8 citation checks) |
| Tool error rate | 0.0 (0/24) | 0.0 (no tools) |
| Provider calls | 20 | 4 |
| Orchestration steps | 28 | 4 |
| Input tokens, conservative fake units | 4,555 | 12,037 |
| Output tokens, conservative fake units | 2,080 | 2,697 |
| Cost, micro-USD | 0 | 0 |

All three separate guard controls matched their expected safe termination: one read-tool failure
returned `tool_failure`/UNKNOWN, one two-step limit returned `step_budget_exceeded`/UNKNOWN and one
pre-cancelled request returned `cancelled`/UNKNOWN without a provider call. A deterministic HOLD
would remain HOLD on a partial path.

Across 25 local repetitions of all four shared cases, the graph measured median 25.8216 ms and p95
30.6005 ms; the non-agent path measured median 0.6696 ms and p95 0.7948 ms. This is Windows/
CPython 3.13.15 in-process fake latency. It excludes real provider, database, queue, network,
sandbox and cold-start time and is not an SLO.

## Decision and limitations

M12 is not promoted and remains disabled by default. It produced no shared-case task-success or
groundedness lift while adding tool/provider calls, graph steps and local latency. The graph is
available as an optional evidence investigation for later representative evaluation.

- Seven designed cases are too small to establish usefulness, safety or generalization.
- M12's exact fact-code check is independently reproducible, but it is not free-text semantic
  entailment.
- The M7 grounding comparison validates citation existence rather than M12's stronger structured
  fact check; the counts are reported separately and are not interchangeable semantic scores.
- Zero fake cost says nothing about hosted-provider billing; no hosted route is enabled.
- Native LangGraph checkpointing is off, so resume/durable-memory behavior is not evaluated.

## Reproduction

```text
uv sync --frozen --group dev --group ai --group agent
uv run python -m eng.evaluate_m7_llm --check
uv run python -m eng.evaluate_m12_agent --check
uv run pytest tests/unit/test_agent_core.py tests/integration/test_agent_investigation_persistence.py tests/web/test_agent_investigation.py
```
