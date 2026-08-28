# Project Status

**Current state: M2 tenancy and GitHub ingestion complete on 2026-08-28.**

The repository now has the M1 foundation plus tenant-scoped identity, signed durable webhook
ingestion, immutable PR snapshots and deterministic advisory/task adapters. No change-intelligence
features, risk engine, benchmark, model metric, customer result, live GitHub adapter validation,
sandbox security claim, or production-readiness claim exists yet.

## Next action

Run `codex-prompts/03_CHANGE_INTELLIGENCE.md` for `RP-0201..RP-0206`. Do not begin dataset/ML work
before M3 deterministic features and blast-radius evidence pass.

## M2 evidence

- Organizations, memberships/roles, GitHub installations/repositories, webhook receipts,
  immutable snapshots, authoritative jobs/outbox rows and append-only audit records have forward
  migrations.
- Composite organization/parent constraints and immutable-record triggers passed on SQLite and
  PostgreSQL 18.6. The full deterministic suite passed **44 tests** on each backend; the separate
  live S3 test was intentionally deselected in these M2 runs.
- Tests cover session/CSRF behavior, login throttling and cache failure, role/IDOR denial, HTTP,
  Celery, admin and management-command scope, signed/tampered/duplicate webhooks, bounded input,
  lifecycle events, immutable checksummed snapshots, broker recovery, bounded retries, duplicate
  task delivery and stale-safe fake advisory publication.
- Strict mypy passed for 107 source files; Ruff, Django checks and migration-drift checks passed.
- GitHub CLI authentication and remote `main` access were repaired, and the configured pre-commit
  and pre-push hooks are installed locally.
- No live GitHub API was called, no installation access token was persisted, and no real check was
  posted. The live snapshot/token/check adapters remain not yet implemented or validated.

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
substitute for a later run on the documented host baseline. The GitHub-hosted workflow is defined;
a remote M2 workflow result has not yet been observed.

| Milestone | Status |
|---|---|
| M0 assessment | Complete — 2026-08-27 assessment plus contradiction/ambiguity correction |
| M1 foundation | Complete — RP-0001..RP-0005 |
| M2 tenancy/GitHub | Complete â€” RP-0101..RP-0106 |
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
