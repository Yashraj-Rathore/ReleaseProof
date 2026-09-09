# 53 — M15 Owner Learning Note

## 1. Concept implemented

M15 turns one source tree into a migration-first, non-root web/worker application image and adds an
immutable release manifest, CI supply-chain checks, protected promotion evidence and safe rollback
rules. It also applies a predeclared evidence gate to optional model-serving technology.

## 2. Why it is used here

A release recommendation system is only credible if the code, model, dataset/evaluation evidence
and database state being reviewed are the same artifacts being promoted. Building once and binding
digests prevents a staging pass from silently approving a different production build. Migration-
first startup prevents new code from serving against an old schema. The serving gate prevents an
extra network service/GPU stack from being introduced without a measured problem it solves.

## 3. Assumptions

- PostgreSQL remains authoritative; Redis/worker health is transport evidence, not product state.
- Compose is a local production-shaped topology, not high availability or public ingress.
- The deterministic risk heuristic remains active; no resident learned model requires extraction.
- Trivy findings depend on the advisory database available during the run.
- GitHub environment protection is configured by a repository Owner outside workflow YAML.
- App/model rollback is safe only inside a proven schema-compatibility window; database recovery is
  a forward fix, never an automatic destructive reverse migration.

## 4. Key code paths

- `deploy/app/Dockerfile`: builder/runtime separation and non-root image.
- `compose.yaml`: migration, web and worker dependency/security/health gates.
- `packages/release_core/contracts.py`: image/model identity, promotion and rollback invariants.
- `eng/release_manifest.py`: build/recompute/verify immutable evidence and promotion receipts.
- `eng/evaluate_m15_release.py`: reproducible conditional-serving and packaging evidence.
- `.github/workflows/ci.yml`: scans, build, SBOM, manifest, live smoke and staging receipt.
- `.github/workflows/release.yml`: ordered protected staging/production attestations.

## 5. Exact rerun

```text
uv run python -m eng.evaluate_m15_release --check
uv run pytest tests/unit/test_release_contracts.py tests/unit/test_m15_packaging.py
uv run --env-file .env.example python -m eng.configure_local
docker compose up --build -d --wait
uv run --env-file .env.example python -m eng.smoke_deployment
docker compose down
```

## 6. Likely interview question

**Why did you not add FastAPI or vLLM when packaging the ML system?**

Because a separate inference service is an operational and security cost, not an automatic upgrade.
The active model is a small deterministic heuristic, and the existing evidence does not measure a
worker memory, cold-start, latency, queueing, dependency-isolation, GPU or independent-scaling
failure. The predeclared gate therefore returns `DEFER_INSUFFICIENT_EVIDENCE`; extraction becomes
appropriate only when a controlled benchmark shows a criterion is violated and the new boundary's
cost is accepted.
