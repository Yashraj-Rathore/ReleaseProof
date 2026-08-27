# Prompt 2 — Tenancy, Identity, GitHub Ingestion

**Assigned issues:** `RP-0101..RP-0106`

Implement organizations/memberships, secure browser sessions/CSRF, GitHub App installation/repository bindings,
signed/deduplicated webhook ingestion, immutable PR snapshots, and advisory check/report adapter behavior.

Use deterministic fakes for tests/demo. Enforce tenant scope on every direct-ID access. Never persist GitHub installation
tokens in plaintext. Do not begin feature extraction or ML.

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
