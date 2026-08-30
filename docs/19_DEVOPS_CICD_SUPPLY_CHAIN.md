# 19 — DevOps, CI/CD and Supply Chain

## Local-first
Fresh clone must reach deterministic demo via documented commands and Docker Compose before Kubernetes.

## CI
Formatting/lint, static typing, unit tests, Django checks/migration drift, Postgres/pgvector integration, secret/dependency scan, template/static checks, contract/evaluation smoke, image build when present, master-spec sync. Expensive training/GPU/sandbox load runs scheduled/manual.

The implemented workflow runs the deterministic suite first on the fast SQLite test backend, then
starts digest-pinned Compose services and reruns it against authoritative PostgreSQL before the live
SeaweedFS contract. This PostgreSQL pass is required for tenant composite-key and append-only-trigger
evidence; SQLite triggers remain a fast mirror, not a substitute. That step supplies an explicit
public test-only webhook signing value because `.env.example` correctly leaves the production
secret blank.

From M4, the same validator also rebuilds the committed synthetic dataset/baseline evidence from
its recorded extraction-code commit and fails when the manifest, feature rows, split assignments,
leakage report, raw predictions, thresholds or metrics drift.

## Planned images
web, worker, migration job, optional model-service, separate runner. Non-root/multi-stage/minimal where feasible; releases use immutable digests.

## Compose
Postgres+pgvector, Redis, SeaweedFS, web, worker; MLflow M13; OTEL/Prometheus/Grafana M14; runner M9 after security gate. SeaweedFS runs single-node for local development only, with an exact image tag and OCI manifest digest, static local-only credentials, a persistent data volume and an authenticated S3 readiness/contract probe.

## Migrations
Migration-first deploy; expand/contract for risky schema changes. Application rollback never blindly reverses destructive migrations.

## Release
Later: semver/tag, immutable image/model IDs, SBOM/provenance, vulnerability gate, staging smoke, protected promotion and compatibility record.

## Kubernetes
Optional and justified only by runner/model/GPU/resource/replica needs. Select one deployment packaging approach by ADR; do not build multiple orchestrator stacks for keywords.
