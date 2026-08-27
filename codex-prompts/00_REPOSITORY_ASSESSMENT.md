# Prompt 0 — Repository Assessment / No Code

Do not create application code, migrations, containers, dependencies, or generated framework files.

Read `AGENTS.md`, `README.md`, `docs/00_DOCUMENT_MAP.md`, `docs/01_PRODUCT_REQUIREMENTS.md`,
`docs/02_SYSTEM_ARCHITECTURE.md`, `docs/07_DATASET_FEATURE_PIPELINE.md`,
`docs/08_CLASSICAL_ML_RISK_ENGINE.md`,
`docs/13_SANDBOX_DIFFERENTIAL_EXECUTION.md`, `docs/15_SECURITY_PRIVACY_TRUST.md`,
`docs/21_TIMELINE_MILESTONES.md`, `docs/22_BACKLOG_AND_ACCEPTANCE.md`,
`docs/26_TECHNOLOGY_BASELINE.md`, and every ADR.

Return:
1. product understanding (max 15 bullets);
2. architecture/trust-boundary graph;
3. proposed initial repository/package structure;
4. exact compatible technology versions, verified against official release/compatibility sources;
5. package/dependency rationale and licenses that need attention;
6. local commands/toolchain;
7. database/extensions/container compatibility;
8. dataset/label/leakage risks;
9. GitHub permission/webhook risks;
10. LLM/RAG/prompt-injection/privacy risks;
11. sandbox threat-boundary risks;
12. contradictions/ambiguities;
13. milestone dependency graph;
14. exact M1 scope;
15. validation commands.

Explicitly call out which planned technologies remain **deferred** and why. Wait for approval after the report.
