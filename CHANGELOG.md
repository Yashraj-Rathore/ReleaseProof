# Changelog

## Unreleased
### Added
- Initial implementation-ready ReleaseProof specification package.
- Product, architecture, database, APIs, GitHub, change intelligence, dataset, ML, semantic-model, RAG, LLM, agent, sandbox, UX, security, testing, MLOps, observability, DevOps, performance, commercialization, runbook, interview, learning and pilot specifications.
- Codex repository instructions, prompts, backlog, ADRs and definition-of-done templates.
- ADR-016 selecting maintained SeaweedFS 4.44 for the bounded local S3 contract.
- ADR-017 defining tenant isolation through server-derived scope, application services and database constraints before optional RLS.
- M1 repository tooling with a Python 3.13.15/uv lock, Ruff, mypy, pytest, pre-commit, and pinned CI actions.
- Pinned PostgreSQL/pgvector, Redis, and SeaweedFS Compose services with persistent local volumes and health checks.
- The canonical ten-app Django modular-monolith skeleton with liveness/readiness endpoints and Celery configuration.
- Provider-neutral GitHub, advisory-LLM, and bounded object-storage seams with deterministic fakes.
- A boto3 S3 adapter, SeaweedFS contract test, idempotent bucket bootstrap, and licensed synthetic fixture repository.
- Vendored HTMX 2.0.10 with a verified SHA-256 checksum.
- Deterministic generation of the Git-ignored SeaweedFS credential config from an explicit local environment file.

### Changed
- Recorded the verified Python 3.13.15/uv/Django/data-service/tooling pins and milestone-gated later dependency snapshots.
- Canonicalized the ten RP-0003 Django module names and policy ownership.
- Made PostgreSQL jobs plus a transactional outbox authoritative across Redis/Celery transport loss.
- Separated generated-test acceptance/export from M9 execution authorization.
- Assigned raw deterministic risk factors to M3 and the first composite evaluated heuristic to M4.
- Added public-dataset source admission, frozen calibration-decision, FTS/embedding index, hosted-provider retention, runner-backend and conditional model-serving gates.
- Replaced vague M13/M14 dependencies with explicit milestone prerequisites.
- Added Boto3 1.43.81 to the Prompt 1 runtime baseline for the ADR-016 S3 adapter.
- Made SeaweedFS readiness wait for a registered writable volume before authenticated S3 bootstrap.

### Evidence status
- M1 implementation evidence is recorded in `PROJECT_STATUS.md`; no product performance, ML quality,
  customer outcome, production-readiness, or sandbox-security claim exists yet.
