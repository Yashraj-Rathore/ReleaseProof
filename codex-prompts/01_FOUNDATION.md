# Prompt 1 — Foundation

**Assigned issues:** `RP-0001..RP-0005`

Build only the verified foundation: Python/Django tooling, production-shaped local data services, modular boundaries,
deterministic provider fakes/fixture repository, CI and documentation synchronization. Do not implement GitHub webhooks,
ML models, embeddings, LLM calls, agents, runner execution, FastAPI, Ollama, vLLM or Kubernetes.

Prove a clean checkout can install, format/lint/type/test, start required local infrastructure and run a deterministic
health/fake-provider smoke test.

Use the exact Prompt 1 pins in `docs/26_TECHNOLOGY_BASELINE.md`, the canonical ten Django app names in `docs/02_SYSTEM_ARCHITECTURE.md`, and SeaweedFS 4.44 under ADR-016. Pin container tags and resolved OCI manifest digests. Prove the bounded object-store contract against the fake and SeaweedFS; do not introduce MinIO or provider-specific types into core packages.

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
