# Prompt 12 — Bounded LangGraph Investigation

**Assigned issues:** `RP-1101..RP-1106`

Implement typed graph state, read-only tools, hard budgets/cancellation/loop guards, an evidence critic, safe human-visible
trace summaries and comparative evaluation.

Agents cannot merge/deploy/write arbitrary repository content. Do not persist hidden chain-of-thought. Compare the agent graph
against the simpler non-agent LLM pipeline; if it does not add value, keep it optional rather than forcing it into production.
Produce Owner Learning Note.

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
