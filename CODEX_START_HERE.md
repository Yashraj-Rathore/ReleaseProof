# Codex Start Here

You are implementing ReleaseProof. Treat repository documentation as source of truth.

> **Current package state:** M0 and M1 were completed on 2026-08-27. The assessment instructions below are retained for reproducibility and should be rerun only when `PROJECT_STATUS.md` marks M0 stale or the technology baseline needs reverification. The current next action is Prompt 2 (`RP-0101..RP-0106`).

## Reproducible M0 assessment — no code

### Read completely
- `AGENTS.md`
- `README.md`
- `docs/00_DOCUMENT_MAP.md`
- `docs/01_PRODUCT_REQUIREMENTS.md`
- `docs/02_SYSTEM_ARCHITECTURE.md`
- `docs/07_DATASET_FEATURE_PIPELINE.md`
- `docs/08_CLASSICAL_ML_RISK_ENGINE.md`
- `docs/13_SANDBOX_DIFFERENTIAL_EXECUTION.md`
- `docs/15_SECURITY_PRIVACY_TRUST.md`
- `docs/21_TIMELINE_MILESTONES.md`
- `docs/22_BACKLOG_AND_ACCEPTANCE.md`
- `docs/26_TECHNOLOGY_BASELINE.md`

Skim all ADRs and report contradictions.

### Verify versions

Using official project documentation/release pages, verify compatible stable versions for every technology selected in `docs/26_TECHNOLOGY_BASELINE.md`. Prefer a conservative Python version supported across Django/PyTorch/HF/scikit-learn deployment tooling rather than novelty.

### Return

1. Product understanding in <=15 bullets.
2. Proposed repository/module structure.
3. Exact versions to pin + official compatibility evidence.
4. Package-manager and validation commands.
5. Architecture dependency graph.
6. Data-model concerns.
7. Dataset provenance/leakage concerns.
8. ML baseline/evaluation plan.
9. RAG/LLM privacy/security concerns.
10. Sandbox threat-model concerns.
11. Requirement contradictions/ambiguities.
12. Milestone dependency graph.
13. Exact Prompt 1 scope.
14. Validation commands for lint/type/test/Django/migrations/containers.
15. What stays fake/deterministic until later milestones.

### Wait

Do **not** initialize frameworks, create migrations, download models, mine GitHub data, call paid LLM APIs, or write product code during this assessment.

## Standard issue prompt

> Implement issue(s) `[IDs]` from `docs/22_BACKLOG_AND_ACCEPTANCE.md`. Read `AGENTS.md`, definition of done, linked docs/ADRs first. Restate scope, implement only those issues, add tests/evaluation evidence, run validation, update docs/status/changelog if needed, regenerate the master spec, and report files changed, commands/results, evidence and remaining risks. Do not start the next issue.
