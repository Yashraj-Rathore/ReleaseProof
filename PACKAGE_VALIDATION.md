# Package Validation

Generated for the ReleaseProof implementation package on 2026-08-30.

## Structural checks

- Numbered source docs: **32** (`00` through `31`)
- ADRs: **17 accepted**
- Canonical backlog issues: **94 unique**
- Codex milestone prompts: **18** (`00` through `17`)
- Reusable templates: **6**
- Canonical Django apps: **10**, with no standalone policy app
- Master-spec synchronization: **PASS**
- `CODEX_MASTER_IMPLEMENTATION_SPEC.md` SHA-256:
  `4438de2d2eca91f16a55511d732423ffe63f5cd3a29c63d82cf62c6c965148d6`

## M1 implementation evidence

- Frozen uv install: **PASS** on CPython 3.13.15 with uv 0.12.6
- Ruff format/lint: **PASS**
- Strict mypy: **PASS**, 64 source files
- Deterministic pytest suite: **PASS**, 25 tests; 1 infrastructure test deselected
- Live SeaweedFS bounded-S3 contract: **PASS**, 1 test
- Django system/deployment checks: **PASS**
- Django migration drift: **PASS**, no project migrations created
- Compose health: **PASS** for PostgreSQL/pgvector, Redis, and SeaweedFS
- Runtime data-service probes: PostgreSQL 18.6, pgvector 0.8.6, Redis 8.10.1,
  SeaweedFS 4.44
- Generated master-spec check and file-inventory check: **PASS**

The local Docker host was Engine 24.0.6 / Compose 2.23.0, not the documented
29.7.2 / 5.4.0 host baseline. The digest-pinned services passed, but a run on the documented host
versions and a remote GitHub Actions run remain unobserved environment evidence, not hidden claims.

## Manual design gates preserved

- PostgreSQL is authoritative; Redis/Celery transport is not product state.
- The Django modular monolith precedes optional service extraction.
- Provider-specific types do not enter framework-light core packages.
- Fake GitHub/LLM/object storage and the synthetic fixture need no paid or remote provider.
- SeaweedFS is limited to ADR-016's tested S3 subset; no full-S3 claim is made.
- No customer code, public GitHub mining, model download, ML training, hosted LLM call, runner,
  FastAPI, Ollama, vLLM, Kubernetes, or product migration was introduced in M1.

## Recommended next action

Run `codex-prompts/05_CLASSICAL_ML_RISK.md` for `RP-0401..RP-0406`. M0 through M4 are complete;
preserve the frozen M4 manifest/split and predeclare M5 training, final-test and calibration gates.

## M2 implementation evidence

- Ruff format/lint: **PASS**
- Strict mypy: **PASS**, 107 source files
- SQLite deterministic suite: **PASS**, 44 tests; live S3 test deselected
- PostgreSQL 18.6 deterministic suite: **PASS**, 44 tests; live S3 test deselected
- Django checks and migration drift: **PASS**
- Signed webhook tamper/dedupe/conflict, CSRF/session/throttle, IDOR/role, composite tenant
  constraints, immutable records, broker recovery, bounded retry, duplicate worker delivery and
  stale advisory behavior: **PASS** in the repository deterministic tests
- Live GitHub API/token minting/check posting: **not yet implemented or validated**

## M3 implementation evidence

- Ruff format/lint: **PASS**
- Strict mypy: **PASS**, 123 source files
- SQLite deterministic suite: **PASS**, 55 tests; live S3 test deselected
- Django system checks and migration drift: **PASS**
- Golden diff/graph/feature/risk-factor artifacts, prediction-time leakage exclusion, explicit
  missing/partial facts, duplicate analysis delivery, append-only persistence and cross-tenant
  denial: **PASS** in repository tests
- Authoritative PostgreSQL deterministic suite and bounded S3 contract: enforced by the GitHub
  Actions Compose gate for this revision
- Composite risk score/evaluated heuristic, live source-tree provider, mined dataset, model and
  hosted-provider behavior: **not implemented or claimed in M3**

## M4 implementation evidence

- Ruff format/lint and strict mypy: **PASS**, 136 source files
- SQLite deterministic suite: **PASS**, 62 tests; live S3 test deselected
- Django system checks, migration drift and Compose configuration: **PASS**
- Frozen synthetic artifact rebuild: **PASS** for 16 rows, exact admission/license provenance,
  feature rows, 6/4/4 temporal train/validation/test assignments, two excluded unknowns and nine
  leakage checks
- Manifest/split hashes: `eab561cbce6cc9986e5b8d9a248b268e3709407dff7f23b111c36c932dd86456`
  / `81d51ed7011c86744f2cf4bff15cb98bb1aa440b1c81ece921ed9b4a21f0c11b`
- Held-out four-row synthetic heuristic evidence: TP=2, FP=2, TN=0, FN=0; precision 0.50,
  recall 1.00 and F1 0.66666667. This validates the harness only and is not a real performance,
  probability, incident, customer or production-readiness claim.
- Tenant/snapshot/feature-bound score persistence, null probability, idempotency, composite
  constraints and append-only controls: **PASS** on SQLite; authoritative PostgreSQL is enforced by
  the GitHub Actions Compose gate for the revision
- Public repository mining, customer data, learned model training and model download: **not done**
