# Prompt 4 — Dataset, Provenance, and Heuristic Baseline

**Assigned issues:** `RP-0301..RP-0306`

Build the formal dataset manifest, approved extraction pipeline, honest proxy labels, leakage-resistant split,
feature materialization and deterministic heuristic baseline/evaluation harness.

Freeze and hash splits before model training. Run duplicate/near-duplicate and future-information leakage checks.
Document why proxy labels are imperfect. Do not report a held-out ML accuracy before an ML model exists.

Do not mine a public repository without the source-admission record in `docs/07_DATASET_FEATURE_PIPELINE.md`. RP-0306 is the first composite heuristic baseline; publish score/band threshold evidence, not probability/calibration claims.

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
