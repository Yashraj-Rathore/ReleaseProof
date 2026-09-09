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

M9 additionally builds the fixture runner from an immutable Python base-image digest and runs the
explicit sandbox marker on the disposable GitHub Linux host. This ephemeral rootful probe is CI
evidence only; ADR-018 requires rootless Docker on a dedicated disposable host for the durable
fixture runner. The runner is not added to the application Compose stack and no application
container receives its Docker socket.

M14 adds digest-pinned OpenTelemetry Collector, Prometheus and Grafana services to the local
Compose dependency graph. Every published port is loopback-only; the services are capability-
dropped and read-only where feasible, Prometheus has bounded local retention, and Grafana disables
anonymous access, self-registration and runtime plugin installation/updates. CI enables OTLP for
one bounded smoke, emits a trace and metric, checks collector health and requires the metric to be
queryable from Prometheus. This is transport evidence, not production alerting, capacity or
authenticated-dashboard evidence.

From M4, the same validator also rebuilds the committed synthetic dataset/baseline evidence from
its recorded extraction-code commit and fails when the manifest, feature rows, split assignments,
leakage report, raw predictions, thresholds or metrics drift.

## Planned images
web, worker, migration job, optional model-service, separate runner. Non-root/multi-stage/minimal where feasible; releases use immutable digests.

## Compose
Postgres+pgvector, Redis, SeaweedFS, web, worker; MLflow M13; OTEL/Prometheus/Grafana M14. The M9
runner remains a separate trust boundary, not a sibling container with access to the Compose host
socket. SeaweedFS runs single-node for local development only, with an exact image tag and OCI
manifest digest, static local-only credentials, a persistent data volume and an authenticated S3
readiness/contract probe.

## Migrations
Migration-first deploy; expand/contract for risky schema changes. Application rollback never blindly reverses destructive migrations.

## Release
Later: semver/tag, immutable image/model IDs, SBOM/provenance, vulnerability gate, staging smoke, protected promotion and compatibility record.

## Kubernetes
Optional and justified only by runner/model/GPU/resource/replica needs. Select one deployment packaging approach by ADR; do not build multiple orchestrator stacks for keywords.

## M15 implementation

M15 adds a multi-stage `deploy/app/Dockerfile` from the existing digest-pinned Python 3.13.15
base. The runtime stage contains one shared application artifact for the migration, web and worker
roles, runs as UID/GID 65532, omits tests/private-model paths/the runner, and uses Gunicorn 26.2.0
for WSGI serving. Compose gates web and worker startup on the successful one-shot migration job and
healthy PostgreSQL, Redis and SeaweedFS dependencies. Application services use read-only root
filesystems, bounded tmpfs/PID/CPU/memory settings, dropped capabilities and
`no-new-privileges`. All published ports remain loopback-only. The separate ADR-018 runner is not
in this stack and no Docker socket is mounted.

The production settings remain fail-closed for secrets and hosts. TLS redirect defaults on and
proxy-header trust defaults off; the explicitly local Compose demo disables redirect and secure
cookies because it publishes only loopback HTTP. The Compose defaults are public local-demo
credentials and are not a production secret-management design. A real deployment must inject
`COMPOSE_DJANGO_SECRET_KEY`/`COMPOSE_GITHUB_WEBHOOK_SECRET`, enable secure cookies and deliberately
configure its trusted TLS proxy.

CI builds `releaseproof-app:m15` once, scans the locked source and exact built image for High/
Critical fixed vulnerabilities, scans the repository for secrets, emits a CycloneDX SBOM, then
records the image ID (`sha256:...`) in `release-manifest-v1`. The manifest also binds the full source
revision, active deterministic model, model registry, synthetic dataset manifest, migration tree,
evaluation bundle, SBOM and local build provenance. The production-shaped Compose smoke, live
fixture sandbox evidence and object-store checks run before the same manifest can receive an
ephemeral staging receipt. Trivy's database is time-varying, so the CI run is the authoritative
scan result rather than a source-controlled claim that future scans will be clean.

`.github/workflows/release.yml` is manual and downloads the immutable evidence from a named
successful CI run. It reverifies the bundle at the exact commit, then crosses the `staging` and
`production` GitHub environments in order without rebuilding or changing the image/model identity.
Repository Owners must configure required reviewers and branch/tag policy on both environments;
workflow YAML cannot create that administrative protection. The workflow records approval
attestations only because no cloud/registry deployment target has been selected. It does not claim
to deploy a live service. Database rollback is always `FORWARD_FIX_ONLY`; an application/model
pointer rollback needs compatibility and smoke evidence and never blindly reverses migrations.

No Kubernetes manifest is added. The one-command production-shaped local start is:

```text
uv run --env-file .env.example python -m eng.configure_local
docker compose up --build -d --wait
```

Use `uv run --env-file .env.example python -m eng.smoke_deployment` to verify web readiness and
migration currency, and `docker compose down` to stop the stack without deleting its volumes.
