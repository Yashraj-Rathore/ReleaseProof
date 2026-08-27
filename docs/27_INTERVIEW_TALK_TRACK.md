# 27 — Interview Talk Track

## 30 seconds
“ReleaseProof is a Python-first change-verification platform. It creates an immutable PR snapshot, computes deterministic blast-radius features, scores a versioned ML risk model, retrieves repository-specific history, proposes targeted tests, and—when allowed—runs base/candidate versions in isolated sandboxes. The final recommendation separates deterministic, ML, retrieval, LLM and execution evidence.”

## Key answers
**Why Django, not only FastAPI?** Django owns product/auth/admin/session/ORM/template concerns; FastAPI is deferred to model-serving isolation, avoiding premature microservices.

**Why HTML/HTMX?** The project needs AI/ML depth more than another SPA; server rendering keeps focus on models/data/security.

**Why classical ML first?** It validates signal/labels and provides explainable/calibratable baseline before deep learning.

**Why PR-AUC?** Positive risk proxies are imbalanced; PR-AUC and threshold precision/recall better describe useful positive detection than ROC-AUC alone.

**Leakage defense?** Temporal/repository splits, diff/commit dedupe, prediction-time-only features, no outcome-derived fields.

**Why pgvector?** Tenant filtering + vectors + relational state in one DB; a dedicated vector service requires a new ADR and benchmark showing the PostgreSQL design misses a predeclared retrieval latency, scale or operational-cost budget and the candidate improves it.

**Why LangGraph?** Explicit bounded state/tool orchestration after single-pass analysis is stable; it does not grant autonomy.

**Biggest security risk?** Arbitrary code execution; runner is a separate trust boundary with no secrets/network by default and explicit limits.

**Hardest ML problem?** Labels. Reverts/hotfixes are proxies; preserve provenance/unknowns and avoid incident claims.

**Scale path?** Separate runner/model pools and perhaps Kubernetes/vector infra only when measured resource/latency requirements justify them.

## Know these topics
Precision/recall/F1/PR-AUC, calibration/Brier, logistic vs XGBoost, transformers/multi-label loss, embeddings/cosine similarity, hybrid retrieval/reranking, RAG eval, prompt injection, Celery idempotency, Postgres transactions, sandbox threat model, MLflow lineage/promotion, OTEL traces.
