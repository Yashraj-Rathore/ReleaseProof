# 50 — M13 Owner Learning Note

## 1. Concept implemented

M13 adds experiment/evaluation lineage, an exact-artifact model registry, human-gated lifecycle and
rollback, delayed deployment-outcome records, and deterministic data-quality/drift assessment. A
pinned MLflow tracking server gives operators a comparison UI and durable run metadata; PostgreSQL
and object storage remain authoritative for its metadata and artifacts.

## 2. Why ReleaseProof uses it

A risk score is defensible only if it can be traced to the exact code, data, features, configuration
and artifact that produced it. Promotion must preserve the rejected/previous alternatives and a
known rollback. Delayed outcomes enable later organization-local learning without relabeling the
historical prediction, while drift checks signal when current inputs or measured behavior no longer
resemble the declared reference.

## 3. Algorithm and data assumptions

- Dataset manifests, feature schemas, code SHAs and artifact checksums are immutable and truthful.
- M4/M5/M6/M7/M11/M12 source artifacts remain authoritative; M13 imports their safe metadata.
- PSI compares the same named feature and same versioned histogram bins. It is not meaningful when
  schemas differ or observed counts are absent.
- A 100-row/100-labeled-row minimum and 0.10 missingness, 0.20 PSI and 0.05 performance-drop limits
  are synthetic starting policy values, not production-calibrated thresholds.
- Revert/hotfix/follow-up style outcomes are proxy signals unless provenance says otherwise.
- Organization-local eligibility never implies shared/global training; customer code is excluded
  from the local unauthenticated MLflow profile.

## 4. Key code paths

- `packages/ml_core/governance.py`: framework-light strict records, lifecycle, feedback and drift.
- `adapters/mlflow/tracking.py`: exact-version, metadata-only, idempotent MLflow client boundary.
- `apps/web/risk/governance_services.py`: role/tenant checks and transactional registry workflows.
- `apps/web/risk/models.py`: immutable artifact/event/outcome/drift/review evidence and deployment
  pointer.
- `eng/evaluate_m13_governance.py`: historical registry import plus drift/rollback fixture evidence.
- `compose.yaml` and `deploy/mlflow/Dockerfile`: pinned local service with PostgreSQL/SeaweedFS.

## 5. Exact experiment/test to rerun

```text
uv run python -m eng.evaluate_m13_governance --check
uv run pytest tests/unit/test_governance.py tests/integration/test_model_governance.py tests/web/test_governance_registry.py
```

For live infrastructure, start Compose, bootstrap the bucket and run
`uv run --env-file .env.example python -m eng.smoke_mlflow`. Run it twice: the second output should
report `created: false` for every exact record hash.

## 6. Likely interview question

**Why is “approved” not a model lifecycle state?**

Approval is evidence about a specific attempted transition: reviewer, reason, evaluation checksum
and compatibility report. Treating it as a state loses whether approval authorized staging,
activation, retirement or rollback. ReleaseProof therefore keeps the operational states
`candidate/staging/active/retired` and records approval on immutable transition events.
