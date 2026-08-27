# Project Status

**Current state: M1 foundation complete on 2026-08-27; M2 has not started.**

The repository now has a runnable Django/Compose/tooling foundation and deterministic provider
fakes. No risk engine, ingestion behavior, benchmark, model metric, customer result, sandbox
security claim, or production-readiness claim exists yet.

## Next action

Run `codex-prompts/02_TENANCY_GITHUB_INGESTION.md` for `RP-0101..RP-0106`. Do not begin
change-intelligence or ML work before the M2 tenant and immutable-ingestion boundaries pass.

## M1 evidence

- `uv sync --frozen --group dev` resolved the committed lock with CPython 3.13.15.
- Ruff format/lint passed; strict mypy passed for 64 source files.
- The deterministic suite passed 25 tests with the one infrastructure test deselected.
- The live SeaweedFS suite passed 1 contract test after authenticated, idempotent bucket bootstrap.
- Django system checks and migration-drift checks passed; only Django's built-in migrations were
  applied to the disposable local PostgreSQL database.
- Compose reported PostgreSQL/pgvector, Redis, and SeaweedFS healthy. Runtime probes reported
  PostgreSQL 18.6, pgvector 0.8.6, and SeaweedFS 4.44; Redis returned authenticated `PONG`.
- `/health/live` and `/health/ready` returned their deterministic healthy payloads with real
  PostgreSQL; the automated failure-path test returns 503 without database details.
- The exact HTMX 2.0.10 checksum test passed, and the network-free fake smoke was repeatable.

The local Docker host was Engine 24.0.6 / Compose 2.23.0 rather than the documented
29.7.2 / 5.4.0 baseline. The digest-pinned services passed on this older host, but that does not
substitute for a later run on the documented host baseline. The GitHub-hosted workflow has been
defined but has not yet produced a remote run in this newly initialized, uncommitted repository.

| Milestone | Status |
|---|---|
| M0 assessment | Complete — 2026-08-27 assessment plus contradiction/ambiguity correction |
| M1 foundation | Complete — RP-0001..RP-0005 |
| M2 tenancy/GitHub | Not started |
| M3 change intelligence | Not started |
| M4 dataset/baseline | Not started |
| M5 classical ML | Not started |
| M6 RAG | Not started |
| M7 LLM evidence | Not started |
| M8 generated tests | Not started |
| M9 sandbox | Not started |
| M10 differential | Not started |
| M11 PyTorch/HF | Not started |
| M12 LangGraph | Not started |
| M13 MLflow/governance | Not started |
| M14 security/ops | Not started |
| M15 containers/CI/model serving | Not started |
| M16 demo/pilot | Not started |
| M17 final review | Not started |
