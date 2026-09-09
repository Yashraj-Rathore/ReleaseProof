# ReleaseProof Implementation Checklist

## Foundation
- [x] Prompt 0/version verification done; no code during assessment.
- [x] Python/Django foundation builds/tests locally.
- [x] PostgreSQL/pgvector, Redis, SeaweedFS S3 endpoint reproducible.
- [x] CI blocks lint/type/test/migration/doc-sync errors.
- [x] Deterministic fake GitHub/LLM + fictional fixture exist.

## Product core
- [x] Tenant/RBAC/CSRF/IDOR protection.
- [x] Signed idempotent GitHub ingestion.
- [x] Immutable PR snapshots.
- [x] Reproducible change features/blast radius.
- [x] Deterministic risk baseline precedes learned models.

## ML/RAG
- [x] Dataset manifests/provenance/labels.
- [x] Time/repository leakage controls.
- [x] Logistic + XGBoost evaluated and versioned; synthetic candidates remain unpromoted.
- [x] Hybrid RAG with tenant isolation/citations.
- [x] PyTorch/HF semantic model + model card; synthetic candidate remains unpromoted.
- [x] MLflow lineage/evaluation.

## LLM/agents
- [x] Strict provider abstraction + fake.
- [x] Grounded structured outputs.
- [x] LangGraph bounded/advisory.
- [x] Critic cannot widen privileges.
- [x] Token/cost/time budgets.

## Execution
- [x] Generated tests are proposals.
- [x] No untrusted host execution.
- [x] Sentinel/network/resource isolation tests for the controlled fixture boundary.
- [x] Base/candidate fixture comparison.
- [x] Mutation/differential evidence integrated safely.

## Engineering/business
- [x] OTEL/log redaction/failure drills.
- [x] Compose before optional Kubernetes.
- [ ] Supply-chain release gates.
- [ ] One-command fictional demo + real screenshots/video.
- [ ] README/resume claims match evidence.
- [ ] Narrow pilot package before broad SaaS scope.
