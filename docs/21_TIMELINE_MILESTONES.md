# 21 — Timeline and Milestones

No calendar promises; advance only when acceptance evidence exists.

| Milestone | Scope | Depends on |
|---|---|---|
| M0 | assessment/version verification | spec |
| M1 | Django/Python foundation + local infra/fakes | M0 |
| M2 | tenancy/auth/GitHub ingestion | M1 |
| M3 | snapshots/change intelligence/blast radius | M2 |
| M4 | datasets/features/heuristic | M3 |
| M5 | logistic + XGBoost | M4 |
| M6 | pgvector/FTS RAG + rerank eval | M3/M4 |
| M7 | strict provider/LLM evidence | M6 |
| M8 | generated tests on fixture | M7 |
| M9 | hardened runner | M8 + accepted RP-0801 isolation ADR |
| M10 | differential/mutation | M9 |
| M11 | PyTorch/HF semantic model | M4/M5 |
| M12 | LangGraph + critic | M7/M10/M11 |
| M13 | MLflow/eval/feedback governance | M12 |
| M14 | consolidated security/observability/reliability/cost hardening | M13 |
| M15 | containers/CI/CD/conditional model serving | M14 |
| M16 | demo/pilot | M15 |
| M17 | final review | M16 |

## Stop conditions
Missing prior evidence, unresolved security boundary, weak/unclear labels/splits, dependency added only for keywords, claims outrunning evidence, or unresolved specification contradiction.

Security, privacy, tenancy, provenance and failure tests are incremental gates in every milestone; M14 consolidates and drills them rather than postponing security work until M14.
