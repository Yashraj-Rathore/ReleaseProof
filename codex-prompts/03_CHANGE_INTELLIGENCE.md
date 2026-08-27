# Prompt 3 — Deterministic Change Intelligence

**Assigned issues:** `RP-0201..RP-0206`

Implement versioned diff normalization, prediction-time feature schema, a bounded Python dependency graph,
deterministic blast radius, pre-change historical statistics, and human-readable evidence.

Keep this milestone deterministic and model-free. Unsupported dynamic imports/languages must be explicit rather than
silently guessed. Add golden fixtures for graph and feature behavior.

Render deterministic risk factors only. Do not create the composite heuristic score, thresholds or recommendation baseline owned by RP-0306.

## Required execution protocol

1. Read `AGENTS.md`, `templates/definition-of-done.md`, `docs/22_BACKLOG_AND_ACCEPTANCE.md`,
   the directly relevant numbered docs and ADRs before changing code.
2. Restate the assigned issue IDs, affected modules/trust boundaries, assumptions and conflicts.
3. Give a small implementation/evaluation plan.
4. Implement **only** the assigned scope.
5. Add/update unit, integration, E2E, security, data, ML or evaluation tests appropriate to the scope.
6. Run exact applicable validation commands and report outcomes; do not report unexecuted targets as results.
7. Update source docs, `PROJECT_STATUS.md` and `CHANGELOG.md` when behavior/evidence changes.
8. Run `python eng/sync_master_spec.py` after source documentation changes and verify `--check`.
9. Report files changed, commands/results, raw evidence/artifacts, remaining risks and the next recommended issue **without implementing it**.
10. For ML/LLM/RAG/agent milestones, include the Owner Learning Note required by `AGENTS.md`.

Never fabricate measurements, customer results, labels, benchmark results, compatibility, security evidence or completion.
