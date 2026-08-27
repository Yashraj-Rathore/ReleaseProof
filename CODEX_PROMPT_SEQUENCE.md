# ReleaseProof — Codex Prompt Sequence

Use **one prompt at a time**. Do not ask Codex to build the whole platform in one task. The canonical prompts live under `codex-prompts/`.

## Prompt order

0. `00_REPOSITORY_ASSESSMENT.md` — read, verify, report, wait; **no code**.
1. `01_FOUNDATION.md` — RP-0001..RP-0005.
2. `02_TENANCY_GITHUB_INGESTION.md` — RP-0101..RP-0106.
3. `03_CHANGE_INTELLIGENCE.md` — RP-0201..RP-0206.
4. `04_DATASET_BASELINE.md` — RP-0301..RP-0306.
5. `05_CLASSICAL_ML_RISK.md` — RP-0401..RP-0406.
6. `06_RAG_RETRIEVAL.md` — RP-0501..RP-0506.
7. `07_LLM_EVIDENCE.md` — RP-0601..RP-0606.
8. `08_GENERATED_TESTS.md` — RP-0701..RP-0704.
9. `09_SANDBOX_RUNNER.md` — RP-0801..RP-0805; threat review first.
10. `10_DIFFERENTIAL_VERIFICATION.md` — RP-0901..RP-0905.
11. `11_PYTORCH_SEMANTIC_MODEL.md` — RP-1001..RP-1006.
12. `12_LANGGRAPH_AGENTS.md` — RP-1101..RP-1106.
13. `13_MLFLOW_GOVERNANCE.md` — RP-1201..RP-1206.
14. `14_SECURITY_RELIABILITY_OBSERVABILITY.md` — RP-1301..RP-1306.
15. `15_CONTAINERS_CICD_MODEL_SERVING.md` — RP-1401..RP-1406; FastAPI/Ollama/vLLM conditional.
16. `16_DEMO_PILOT.md` — RP-1501..RP-1506.
17. `17_FINAL_ARCHITECTURE_REVIEW.md` — RP-1601..RP-1603; review only.

## Standard single-issue prompt

> Implement issue `[RP-XXXX]` from `docs/22_BACKLOG_AND_ACCEPTANCE.md`. Read `AGENTS.md`, `templates/definition-of-done.md`, the issue, directly relevant numbered docs and ADRs. Restate scope and trust boundaries; implement only that issue; add tests/evaluation; run exact validation; update docs/status/changelog when needed; regenerate and check `CODEX_MASTER_IMPLEMENTATION_SPEC.md`; report files changed, commands/results, evidence, remaining risk and the next suggested issue without starting it. For ML/AI work, include the Owner Learning Note.

## Defect-fix prompt

> Investigate defect `[description]`. Read the source-of-truth docs first. Reproduce with a failing automated test where practical, identify root cause, make the smallest safe correction, run targeted and relevant full regressions, update contracts/docs only when required, and report evidence plus remaining risk. Do not implement unrelated backlog work.

## ML-regression prompt

> Investigate ML regression `[description]`. Freeze the dataset/split/model/evaluation versions first. Check data/label leakage, schema drift, preprocessing parity, calibration, environment and random-seed variance before changing modeling. Compare against the prior baseline using the same held-out evaluation, publish raw before/after artifacts and limitations, and do not tune on the held-out test set.

## RAG / LLM / agent regression prompt

> Investigate `[retrieval/LLM/agent issue]` using the frozen evaluation fixtures and exact provider/model/prompt/embedding/reranker/graph versions. Separate retrieval failure, evidence-selection failure, schema failure, unsupported claim, tool failure and orchestration failure. Make the smallest justified change and rerun both quality and cost/latency evaluations. Do not rely only on model self-grading.

## Security-review prompt

> Review `[scope]` against `docs/15_SECURITY_PRIVACY_TRUST.md`, `docs/13_SANDBOX_DIFFERENTIAL_EXECUTION.md`, applicable ADRs and `AGENTS.md`. Do not patch automatically. Rank exploitable/unsafe conditions by severity with evidence, trust boundary, data exposure, minimal remediation and residual risk. Never print discovered secrets or private source.

## Architecture-review prompt

> Review implementation against `docs/02_SYSTEM_ARCHITECTURE.md`, the data/ML/RAG/runner contracts and all ADRs. Do not refactor automatically. Return violations ranked by severity with file/evidence references, dependency/complexity concerns and a staged correction plan.

## Hard gates

- No formal model work before immutable dataset/split evidence.
- No untrusted execution before runner threat review.
- No probability wording without held-out calibration evidence.
- No agentic complexity without comparison to the simpler pipeline.
- No FastAPI/Ollama/vLLM/Kubernetes solely for keywords.
- No public performance/accuracy/customer-impact claim without reproducible evidence.
