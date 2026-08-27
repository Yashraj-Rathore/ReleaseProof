# Prompt 9 — Hardened Sandbox Runner

**Assigned issues:** `RP-0801..RP-0805`

FIRST complete `RP-0801` as a written threat review and add the required accepted isolation-backend ADR. If any Critical/High boundary cannot be acceptably mitigated in the planned local runner, STOP and report it before implementing execution. A generic shared-host Docker setup is not an implicit approval for hostile external code.

Only after the review passes, implement the narrow versioned execution-plan/result contracts and isolated execution for the
controlled fixture repository. Never mount the host Docker socket, inject cloud/customer secrets, grant unrestricted egress,
or run repository code on the Django/Celery host. Implement the separate audited execution-approval transition bound to exact snapshot/proposal/plan hashes, sentinel escape/resource/cleanup tests and Owner Learning Note.

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
