# 16 — Testing, Quality and Evaluation

## Test pyramid
### Unit
Domain invariants, feature extraction, graph algorithms, schemas, thresholds, retrieval fusion, LLM validation, recommendation policy, execution-plan hashing.

### Integration
Real Postgres/pgvector, Redis, the pinned SeaweedFS S3 endpoint and controlled HTTP adapters/Testcontainers where useful. The object-store contract suite covers bucket readiness plus bounded put/head/get/delete, checksum, missing-object and unavailable-provider behavior; it must also pass against the deterministic fake.

### Contract
GitHub fixtures, provider schemas, model service, runner plan/results.

### Browser E2E
Playwright for demo/login/repository/PR evidence/policy/proposal/degradation flows.

## ML evaluation
Pinned manifest + split + feature version. CI uses smoke inference on pinned artifacts; expensive training/eval runs separately. Check train/serve consistency, leakage, prevalence, baseline comparison, threshold metrics, calibration and artifact checksum.

## RAG evaluation
Frozen relevance set; Recall@K/MRR/nDCG where applicable, latency, cross-tenant isolation; compare lexical/vector/hybrid/reranked.

## LLM/agent evaluation
Schema validity, evidence citations, unsupported claims, prompt injection, missing/conflicting components, budgets, max-step enforcement. Deterministic/human gold checks required even when an LLM judge is used.

## Sandbox E2E
Base-pass/candidate-fail planted regression, identical-change no invented regression, timeout, blocked network, unavailable sentinel secret, output limit, mismatched SHA/plan rejection.

## Performance
Correctness first. Raw artifacts + environment. Targets never become claims without executed evidence.

Coverage percentage is secondary to explicit tests of critical tenancy/security/model/sandbox branches.
