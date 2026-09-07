# 49 — M13 Governance Evaluation

## Scope and decision

M13 implements `RP-1201..RP-1206` without changing the product's active inference decision. The
deterministic heuristic remains the fixture/demo baseline; M5 and M11 learned artifacts remain
unpromoted because their published gates failed. All evidence in this document is synthetic or
approved public metadata. It is not customer-quality, production-drift or incident evidence.

Approval is immutable evidence attached to a transition, not a lifecycle state. The canonical
lifecycle is `candidate -> staging -> active -> retired`; rollback is the explicit
`retired -> active` transition. This resolves the earlier `candidate -> approved -> retired`
shorthand in docs/03 and docs/17 against the M13 acceptance vocabulary in docs/22.

## RP-1201 — tracking deployment

- The application dependency group pins `mlflow-skinny==3.15.2`; it is the remote tracking client
  and does not force MLflow's pandas `<3` server/data-science dependency onto the M5 pandas 3.0.5
  environment.
- `deploy/mlflow/Dockerfile` separately pins the full `mlflow==3.15.2` server, Python 3.13.15 base
  image digest, Boto3 1.43.81 and psycopg 3.3.4.
- Compose uses PostgreSQL as the backend store and proxied SeaweedFS S3 storage at
  `s3://releaseproof-local/mlflow`. There is no MLflow local-volume source of truth.
- The service is loopback-published, non-root, capability-free, read-only-root, bounded to one
  worker and configured with explicit allowed-host/CORS settings. This is a development profile,
  not an authenticated multi-tenant production control plane. Customer-data records are rejected
  by the ReleaseProof adapter.
- `/health` and `/version` are checked; `eng.smoke_mlflow` requires exact client/server 3.15.2 and
  idempotently registers the source-controlled records after the S3 bucket bootstrap.

`docker compose config --quiet` passed locally. A live server build/smoke was not measured on the
assessment host because its Docker daemon was unavailable; the CI workflow owns that Linux check.

## RP-1202 — formal experiment lineage

`formal-experiment-v1` requires experiment/run/kind, dataset version and manifest SHA-256, feature
schema, immutable code SHA, bounded parameters and metrics, environment, immutable artifact URIs
and checksums, data scope, synthetic status and customer-content status. M13 imports three already
published histories without rewriting them:

| Experiment | Historical source | Decision |
|---|---|---|
| deterministic heuristic | M4 | active for fixture/demo |
| logistic/XGBoost classical candidates | M5 | candidate, not promoted |
| MiniLM semantic head candidate | M11 | candidate, not promoted |

The M4 environment field is explicitly marked `m13_historical_import`; it does not claim that M4
was originally executed by MLflow. The authoritative pre-existing raw artifacts and hashes remain
unchanged.

## RP-1203 — evaluation registry

`evaluation-registry-entry-v1` contains only configuration versions, frozen dataset identity,
aggregate metrics, immutable result-artifact identity, license and synthetic/customer-code flags.
It registers:

| Component | Dataset | Registry record SHA-256 |
|---|---|---|
| retrieval | `m6-relevance-fixture-v1` | `9128135b4aace2198872e8f5442b9144f688a6eb6c33eb4591e26e9fbdd9ae33` |
| LLM | `m7-grounding-fixture-v1` | `b231c1f4e076fc09df5069a4b2505320a1008b59c81a044294089854c0fd7229` |
| agent | `m12-agent-fixture-v1` | `265ce859e936d99ae5e0d9e9b7921c11bb0bccf6d913c8034b50120061fbdb30` |

The authenticated active-organization endpoint `GET /api/v1/evaluations/latest` exposes this safe
registry. It does not expose source, prompts, raw provider responses, traces or customer code.

## RP-1204 — promotion and rollback

`GovernedModelArtifact` stores an exact immutable artifact/data/experiment/schema/runtime identity.
Append-only `ModelLifecycleEvent` rows store sequence, transition, reviewer, reason, evaluation
hash and the exact six-check compatibility report: artifact checksum, evaluation gate, feature
schema, input schema, privacy/license and runtime. Each approval checksum binds the exact artifact,
authorized action, reviewer identity/role, reason, evaluation and compatibility report. Owner/Admin
identity must match the approval; replacement and rollback require separate retirement evidence.

`ModelDeployment` is the only mutable pointer. Its active and rollback artifacts update in one
database transaction and each update increments a generation. Cross-organization relationships
are rejected by application scoping and composite database constraints. A deterministic two-
artifact test exercises activation, replacement and rollback; append-only triggers reject raw
artifact/event mutation. No learned artifact is promoted by M13.

## RP-1205 — delayed outcomes

`DeploymentOutcome` is append-only and binds organization, repository, immutable snapshot and the
original `RiskScore.result_hash`. The explicit taxonomy is `no_issue`, `revert`, `hotfix`,
`incident`, `manual_label`, or `unknown`. Ingestion requires a 30–365 day observation window,
timezone-aware ordered timestamps and completed-window delay. Organization-local training
eligibility additionally requires known provenance, organization learning enabled and explicit
per-outcome opt-in. `shared_training_eligible` is permanently false. Recording an outcome never
updates the prediction it describes.

## RP-1206 — data quality and drift

`data-quality-drift-policy-v1` compares exact feature schemas, missingness deltas, population
stability index over versioned bins and labeled performance drop. It requires at least 100 feature
rows and 100 labeled rows. Decisions are `pass`, `review`, `insufficient_data`, or
`incompatible_schema`.

The CC0 aggregate fixture exercises all four decisions. The shifted case detects missingness,
distribution and performance changes. Insufficient samples do not become a drift claim. Every
non-pass requires an append-only human review, and both automatic retraining and automatic
promotion are false in the contract, database and persisted report.

## Reproduction

```text
uv sync --frozen --group dev --group ml --group ai --group semantic --group agent --group governance
uv run python -m eng.evaluate_m13_governance --check
uv run pytest tests/unit/test_governance.py tests/integration/test_model_governance.py tests/web/test_governance_registry.py
uv run --env-file .env.example python -m eng.configure_local
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example up -d --build --wait
uv run --env-file .env.example python -m eng.bootstrap_object_store
uv run --env-file .env.example python -m eng.smoke_mlflow
```

The committed evaluation root is
`b399c842d816932d4de007067f351bc1b34f0d384c34d3c15464ca5bda503f44`. Its drift profiles are
aggregate synthetic controls, its rollback drill validates mechanics only, and its MLflow records
are an M13 registration of historical evidence rather than proof that past milestones used MLflow.
