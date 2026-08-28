# ReleaseProof Implementation Checklist

## Foundation
- [x] Prompt 0/version verification done; no code during assessment.
- [x] Python/Django foundation builds/tests locally.
- [x] PostgreSQL/pgvector, Redis, SeaweedFS S3 endpoint reproducible.
- [x] CI blocks lint/type/test/migration/doc-sync errors.
- [x] Deterministic fake GitHub/LLM + fictional fixture exist.

## Product core
- [ ] Tenant/RBAC/CSRF/IDOR protection.
- [ ] Signed idempotent GitHub ingestion.
- [ ] Immutable PR snapshots.
- [x] Reproducible change features/blast radius.
- [ ] Deterministic risk baseline precedes learned models.

## ML/RAG
- [ ] Dataset manifests/provenance/labels.
- [ ] Time/repository leakage controls.
- [ ] Logistic + XGBoost evaluated and versioned.
- [ ] Hybrid RAG with tenant isolation/citations.
- [ ] PyTorch/HF semantic model + model card.
- [ ] MLflow lineage/evaluation.

## LLM/agents
- [ ] Strict provider abstraction + fake.
- [ ] Grounded structured outputs.
- [ ] LangGraph bounded/advisory.
- [ ] Critic cannot widen privileges.
- [ ] Token/cost/time budgets.

## Execution
- [ ] Generated tests are proposals.
- [ ] No untrusted host execution.
- [ ] Sentinel/network/resource isolation tests.
- [ ] Base/candidate fixture comparison.
- [ ] Mutation/differential evidence integrated safely.

## Engineering/business
- [ ] OTEL/log redaction/failure drills.
- [ ] Compose before optional Kubernetes.
- [ ] Supply-chain release gates.
- [ ] One-command fictional demo + real screenshots/video.
- [ ] README/resume claims match evidence.
- [ ] Narrow pilot package before broad SaaS scope.
