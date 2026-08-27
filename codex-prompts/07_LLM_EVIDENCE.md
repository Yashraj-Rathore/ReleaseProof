# Prompt 7 — Evidence-Grounded LLM Analysis

**Assigned issues:** `RP-0601..RP-0606`

Implement typed LLM provider contracts/fake, one hosted adapter, privacy-aware routing, versioned prompts/schemas,
grounded analysis and frozen evaluation.

Require strict structured validation and cited evidence IDs for evidence-bearing claims. Do not store hidden chain-of-thought.
Provider failure or unsupported evidence yields safe partial/UNKNOWN behavior. Hosted source transmission must obey tenant
policy. Produce an evaluation report and Owner Learning Note.

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
