# 52 — M15 Production Packaging and Release Evidence

## Scope and outcome

M15 implements RP-1401, RP-1405 and RP-1406 and completes the conditional RP-1402, RP-1403 and
RP-1404 decision records. It packages the existing Django modular monolith and Celery worker; it
does not widen product behavior, enable external repository execution, promote a learned model or
add Kubernetes.

## Image and Compose topology

`deploy/app/Dockerfile` is a two-stage image built from the same immutable Python 3.13.15 OCI digest
used by the controlled fixture runner. The builder installs exact locked runtime groups and creates
static assets. The runtime copies only the environment plus application adapters, Django apps,
framework-light packages, workers, public model metadata and the active governance artifact. It
does not copy tests, private model/data paths, Git metadata or the runner. UID/GID 65532 runs the
image and Gunicorn 26.2.0 serves WSGI.

The same `releaseproof-app:m15` build is used for three roles:

- `migration` waits for healthy PostgreSQL and completes `migrate --noinput` once;
- `web` starts only after migration success and healthy Redis/SeaweedFS, then exposes loopback port
  8000 with liveness/readiness checks;
- `worker` starts only after the same gates and exposes no host port.

All three drop Linux capabilities, set `no-new-privileges`, use a read-only root filesystem and
bounded tmpfs, PID, memory and CPU settings. Web/worker have an init process and bounded graceful
shutdown. `SANDBOX_ENABLED=false` is fixed in the application environment. The fixture-only runner
remains outside Compose, gets no application credential and shares no Docker socket.

The local demo deliberately uses known local-only default credentials and loopback HTTP. Production
settings still reject missing/short application and webhook secrets. TLS redirect and secure
cookies default true outside this explicitly local Compose override, and forwarded-protocol trust
is opt-in. A deployed Compose instance must inject the two `COMPOSE_*_SECRET` variables rather than
using the public demo defaults. This is a production-shaped reproducible topology, not a public/HA
production deployment.

## Supply-chain gates

The main CI job now performs these fail-closed steps before emitting promotion evidence:

1. canonical format/lint/type/test/Django/migration/evaluation validation;
2. Trivy 0.74.0 scan of locked dependencies for fixed High/Critical vulnerabilities;
3. Trivy secret scan of the checked-out repository;
4. one production application-image build;
5. High/Critical fixed-vulnerability scan of that exact local image ID;
6. CycloneDX JSON SBOM generation;
7. `release-manifest-v1` binding source/image/model/data/migrations/evaluations/SBOM/provenance;
8. migration-first Compose startup and bounded live deployment smoke;
9. authoritative PostgreSQL, telemetry, fixture sandbox, SeaweedFS and MLflow evidence;
10. an ephemeral staging receipt for the unchanged release manifest and artifact upload.

`release-manifest-v1` rejects mutable image tags and external-repository execution. It records the
full source commit, exact application `sha256:` image ID, active deterministic model hash, M5 model-
registry manifest checksum, M4 synthetic dataset file and internal manifest checksums, migration
tree, evaluation bundle, CycloneDX SBOM and a checksum over Dockerfile/lock/source/image build
provenance. Verification recomputes those bindings from the checked-out revision.

Trivy findings are evaluated at CI time against its downloaded advisory database. The source-
controlled M15 artifact proves gate configuration and deterministic contracts, not the absence of
future CVEs. Local provenance is checksum-bound but unsigned. Registry/OIDC provenance remains
deferred because no registry/deployment target is selected.

## Promotion and rollback

The manual protected-release workflow takes a successful CI run ID and full source commit. It
downloads the named immutable CI artifact, checks out exactly that revision, and recomputes the
manifest. The same bundle then crosses GitHub `staging` and `production` environments in order.
Each receipt retains the original manifest/image/model hashes and requires migrations, evaluations,
smoke and compatibility evidence before approval.

The workflow is an approval/evidence contract, not a cloud deployment adapter. A repository Owner
must configure required reviewers and branch/tag protection for both GitHub environments before
using it for a real release. There is no implicit rebuild, `docker push`, provider credential or
deployment command.

Rollback changes only to a previously recorded compatible application/model release after target
smoke evidence. The database strategy is always `FORWARD_FIX_ONLY`; ReleaseProof never blindly
reverses an applied destructive migration. Risky future schema work must use expand/contract and
provide a compatible target window.

## Conditional model-serving decisions

The predeclared docs/20 budget is 768 MiB resident model memory per worker, 10 s cold start,
250 ms steady p95, at least 4 records/s, 2 s queue-delay p95 and at most USD 75/month incremental
infrastructure. These are decision hypotheses, not achieved SLOs.

| Issue | Decision | Evidence gap |
|---|---|---|
| RP-1402 FastAPI | `DEFER_INSUFFICIENT_EVIDENCE` | no active resident learned model; worker RSS/startup, broker delay/saturation and independent scaling economics not measured |
| RP-1403 Ollama | `DEFER_INSUFFICIENT_EVIDENCE` | no approved local-privacy demand, hardware/model/license selection or schema/grounding evaluation |
| RP-1404 vLLM | `DEFER_INSUFFICIENT_EVIDENCE` | no failing simple baseline, approved GPU/model/privacy review or measured throughput/cost benefit |

No optional service or package is scaffolded. Revisit only by updating the predeclared workload,
running a controlled comparison and accepting the new operational/security boundary.

## Reproduction

```text
uv sync --frozen --group dev --group ml --group ai --group semantic --group agent --group governance --group observability
uv run python -m eng.evaluate_m15_release --check
uv run pytest tests/unit/test_release_contracts.py tests/unit/test_m15_packaging.py
uv run --env-file .env.example python -m eng.configure_local
docker compose config --quiet
docker build --file deploy/app/Dockerfile --tag releaseproof-app:m15 .
docker compose up -d --wait
uv run --env-file .env.example python -m eng.smoke_deployment
docker compose down
```

The committed `m15-release-evaluation-v1` artifact is deterministic, synthetic contract evidence.
It does not claim production capacity, cloud deployment, hosted/local-provider quality, GPU
performance or Kubernetes readiness.
