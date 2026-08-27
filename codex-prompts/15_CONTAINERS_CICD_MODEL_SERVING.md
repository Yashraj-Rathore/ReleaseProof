# Prompt 15 — Production Packaging, CI/CD, Conditional Model Serving

**Assigned issues:** `RP-1401..RP-1406`

Create production images/Compose, CI/CD and supply-chain gates, plus staging promotion/rollback contracts.

`RP-1402` FastAPI, `RP-1403` Ollama and `RP-1404` vLLM are **conditional**. For each, first profile/document the concrete
need. It is acceptable—and preferred—to mark an issue deliberately deferred when independent scaling, local privacy mode,
GPU serving/hardware or measurable benefit is absent. Never add them only to enlarge the resume stack. Kubernetes remains
outside this milestone unless a source-doc/ADR update with evidence explicitly approves it.

For RP-1402, predeclare the workload and numeric budgets and use the decision vocabulary/criteria in `docs/20_PERFORMANCE_CAPACITY_COST.md`. A deferral decision satisfies the conditional issue when supported by the required evidence; do not scaffold an unused service.

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
