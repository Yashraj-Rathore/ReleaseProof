# Prompt 17 — Final Architecture / Security / ML Claims Review

**Assigned issues:** `RP-1601..RP-1603`

REVIEW ONLY. Do not refactor or patch automatically.

Review source-of-truth compliance, architecture drift, security/privacy, runner isolation, data provenance/leakage,
held-out/calibration evidence, model cards, retrieval/LLM/agent evaluation, operational evidence, dependency justification,
public README/demo/resume claims and pilot readiness.

Rank findings with file/evidence references and return exactly one decision:
`READY_FOR_DEMO`, `READY_FOR_NARROW_PILOT`, or `NOT_READY`.
Provide a staged correction queue for unresolved findings.

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
