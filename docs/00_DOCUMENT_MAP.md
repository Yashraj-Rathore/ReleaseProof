# 00 — Document Map

| Document | Purpose |
|---|---|
| `01_PRODUCT_REQUIREMENTS.md` | users, jobs, MVP, invariants, success evidence |
| `02_SYSTEM_ARCHITECTURE.md` | module/deployable/trust boundaries |
| `03_DOMAIN_AND_DATABASE.md` | tenancy, snapshots, evidence, model/data persistence |
| `04_API_AND_CONTRACTS.md` | browser/API/model/runner contracts |
| `05_GITHUB_INTEGRATION.md` | GitHub App, webhooks, source/status behavior |
| `06_CHANGE_INTELLIGENCE_BLAST_RADIUS.md` | deterministic diff/graph/features |
| `07_DATASET_FEATURE_PIPELINE.md` | labels, provenance, leakage and train/serve features |
| `08_CLASSICAL_ML_RISK_ENGINE.md` | heuristic, sklearn, XGBoost, calibration |
| `09_SEMANTIC_MODEL_PYTORCH_HF.md` | deep-learning semantic classifier |
| `10_RAG_RETRIEVAL_RERANKING.md` | pgvector/FTS hybrid retrieval and evaluation |
| `11_LLM_PROVIDER_AND_ANALYSIS.md` | providers, strict outputs, privacy, prompt injection |
| `12_LANGGRAPH_AGENT_ORCHESTRATION.md` | bounded agent state/tools/critic |
| `13_SANDBOX_DIFFERENTIAL_EXECUTION.md` | generated tests, isolation, differential/mutation |
| `14_FRONTEND_UX.md` | HTML/CSS/Django/HTMX product UI |
| `15_SECURITY_PRIVACY_TRUST.md` | auth, source privacy, tenant/AI/sandbox threats |
| `16_TESTING_QUALITY_EVALUATION.md` | test pyramid + ML/RAG/LLM/sandbox eval |
| `17_MLOPS_MODEL_GOVERNANCE.md` | MLflow, lineage, promotion, feedback/drift |
| `18_OBSERVABILITY_OPERATIONS.md` | logs, metrics, traces, controls |
| `19_DEVOPS_CICD_SUPPLY_CHAIN.md` | Docker/CI/releases/optional Kubernetes |
| `20_PERFORMANCE_CAPACITY_COST.md` | measurement and budget methodology |
| `21_TIMELINE_MILESTONES.md` | ordered dependencies |
| `22_BACKLOG_AND_ACCEPTANCE.md` | issue IDs and acceptance |
| `23_DEMO_PORTFOLIO.md` | recruiter demo and claim evidence |
| `24_COMMERCIALIZATION.md` | ICP, pilot, pricing hypotheses |
| `25_FAILURE_MODES_RUNBOOKS.md` | operational recovery |
| `26_TECHNOLOGY_BASELINE.md` | dated pinning/verification policy |
| `27_INTERVIEW_TALK_TRACK.md` | architecture/ML explanations |
| `28_NON_GOALS_FUTURE.md` | deliberate exclusions |
| `29_PILOT_PACKAGE.md` | pilot onboarding/measurement |
| `30_LEARNING_CHECKPOINTS.md` | owner learning plan |
| `31_FINAL_ARCHITECTURE_REVIEW.md` | final claim/security/architecture audit |
| `32_M5_CLASSICAL_MODEL_CARD.md` | exact M5 lineage, measurements, calibration and promotion decision |
| `33_M5_OWNER_LEARNING_NOTE.md` | owner-defensible M5 concepts, assumptions and rerun path |
| `34_M6_RETRIEVAL_EVALUATION.md` | exact retrieval configuration, frozen measurements and activation decision |
| `35_M6_OWNER_LEARNING_NOTE.md` | owner-defensible M6 concepts, assumptions and rerun path |
| `36_M7_LLM_EVALUATION.md` | strict-schema grounding evaluation, configuration, measurements and limitations |
| `37_M7_OWNER_LEARNING_NOTE.md` | owner-defensible M7 contracts, privacy routing and rerun path |

ADRs under `docs/decisions/` explain choices that must not be casually reversed.
