# AGENTS.md — Repository Instructions for Codex

## Mission

Build and maintain ReleaseProof according to this repository. ReleaseProof analyzes software changes, estimates risk, retrieves historical evidence, proposes targeted tests, executes untrusted candidate code only inside hardened sandboxes, compares base/candidate behavior, and returns advisory evidence to a human reviewer.

## Required reading

Before any change:
1. `README.md`
2. `docs/01_PRODUCT_REQUIREMENTS.md`
3. `docs/02_SYSTEM_ARCHITECTURE.md`
4. documents linked to the assigned issue
5. relevant ADRs in `docs/decisions/`
6. `docs/22_BACKLOG_AND_ACCEPTANCE.md`
7. `templates/definition-of-done.md`

For ML/LLM issues also read:
- `docs/07_DATASET_FEATURE_PIPELINE.md`
- `docs/08_CLASSICAL_ML_RISK_ENGINE.md`
- `docs/09_SEMANTIC_MODEL_PYTORCH_HF.md`
- `docs/10_RAG_RETRIEVAL_RERANKING.md`
- `docs/16_TESTING_QUALITY_EVALUATION.md`
- `docs/17_MLOPS_MODEL_GOVERNANCE.md`

`CODEX_MASTER_IMPLEMENTATION_SPEC.md` is generated. Never edit it directly. If requirements conflict, report the conflict instead of inventing a new direction.

## Architecture rules

- Start as a **Django modular monolith** with separate Celery workers.
- Keep domain/ML algorithms framework-light; core packages must not depend on Django requests/templates/Celery task objects.
- Add FastAPI model serving only when RP-1402 satisfies the predeclared measurement gate and decision vocabulary in `docs/20_PERFORMANCE_CAPACITY_COST.md`.
- PostgreSQL is authoritative.
- pgvector + PostgreSQL FTS are the first retrieval stores.
- Redis is broker/cache/coordination support, never authoritative product state.
- Use S3-compatible storage for large immutable artifacts; SeaweedFS locally per ADR-016.
- Complete Docker Compose before Kubernetes.
- Do not add Kafka, Airflow, Pinecone, Weaviate, Milvus, Spark, Ray, Kubernetes, or GPU serving merely for résumé keywords.
- Web UI: HTML/CSS + Django templates + HTMX + minimal JS.
- Browser mutations use session auth + CSRF; no long-lived secrets in localStorage.

## Python rules

- Use the verified baseline from `docs/26_TECHNOLOGY_BASELINE.md`.
- Thin views/controllers; business logic in application/domain services.
- Explicit types and strict boundary schemas.
- Validate and bound all external input.
- Explicit network/database/provider timeouts.
- Never swallow exceptions or retry permanent failures blindly.
- Never log GitHub tokens, OAuth tokens, cookies, Authorization headers, LLM keys, secrets, or arbitrary customer source content.
- No hard-coded tenant/repository IDs, credentials, pricing, or demo accounts in production code.
- Every dependency must solve a documented problem.

## GitHub rules

- GitHub App with least-privilege permissions.
- Verify webhook signatures before trusted parsing.
- Delivery/event handling is idempotent.
- Installation tokens are short-lived and never persisted in plaintext.
- Tenant/repository identity is server-derived.
- Persist only content allowed by retention policy.

## ML/data rules

- **No invented training data.** Synthetic data must be marked synthetic and separated from real evaluation claims.
- Preserve dataset provenance, extraction version, label rule, feature version, usage/license notes, observation window, and split assignment.
- Default headline evaluation is time-aware and repository-aware; random row splits are insufficient.
- Train/validation/test boundaries are immutable after experiment publication.
- Revert/hotfix/follow-up labels are proxies, not “incidents.”
- Start with a deterministic heuristic baseline before ML.
- Learned models must beat or complement baselines before promotion.
- If a displayed number is called a probability, calibration must be measured.
- Report prevalence, precision, recall, F1, PR-AUC, ROC-AUC as secondary context, threshold behavior, and calibration where applicable.
- Customer code is not used for shared/global training by default. Organization-local learning is explicit opt-in.
- Model artifacts are immutable/versioned and loaded by exact identifier/checksum.

## LLM/RAG rules

- LLM output is untrusted structured suggestion, never authority.
- Reject invalid provider output instead of silently coercing it.
- RAG evidence preserves source references.
- Hosted-provider transmission of customer code obeys organization policy.
- Deterministic fake provider is mandatory for tests/demo.
- Prompts, model identifiers, embedding versions, and graph schemas are versioned.
- Never let an LLM merge/deploy, access secrets, or widen sandbox permissions.
- Agent graphs have max steps, wall time, token/cost budgets, and tool allowlists.
- A critic using the same model does not count as independent validation by itself.

## Sandbox rules

- **Never execute untrusted repository code on the application host.**
- No host Docker socket, production/cloud credentials, repo write token, SSH agent, or unrestricted host mounts.
- Network denied by default.
- Non-root, resource/PID/time/output limits, ephemeral volumes, read-only filesystem where feasible.
- Treat sandbox output as untrusted.
- Any credible sandbox escape concern blocks the execution milestone.

## Testing rules

Every behavior change must add/update appropriate unit, integration, evaluation, and critical E2E tests and report exact commands/results.

Critical evidence includes:
- signed webhook -> immutable snapshot -> analysis;
- duplicate webhook harmless;
- cross-org IDOR denied;
- unavailable LLM does not erase deterministic evidence;
- invalid LLM schema rejected;
- every risk score names artifact/feature version;
- leakage checks fail closed;
- cross-tenant RAG query fails;
- generated tests remain proposals until M8 human acceptance; execution additionally requires the separate M9 execution approval bound to an immutable proposal and plan hash;
- candidate cannot read sentinel host/control secrets;
- base/candidate fixture comparison reproducible;
- failed sandbox/provider becomes REVIEW/UNKNOWN rather than false SHIP;
- model/prompt/retrieval regressions are detectable.

## Truthfulness rules

A target is not a measurement. A synthetic demo is not a customer outcome. A proxy label is not a production incident. If evidence is missing, write “not yet measured” or “not yet validated.”

## Learning protocol

For ML/AI milestones, completion reports include an **Owner Learning Note**:
1. concept implemented;
2. why it is used here;
3. algorithm/data assumptions;
4. key code paths;
5. exact experiment/test to rerun;
6. one likely interview question + concise answer.

Do not hide core ML implementation behind abstractions the owner cannot explain.

## Task execution protocol

For every assigned issue:
1. Restate IDs/components.
2. Read linked docs/ADRs.
3. State assumptions/conflicts.
4. Give a small plan.
5. Implement only assigned issues.
6. Add tests/evaluation evidence.
7. Run validation.
8. Update source docs, `PROJECT_STATUS.md`, `CHANGELOG.md` if behavior changes.
9. Run `python eng/sync_master_spec.py` after source-doc changes.
10. Report files changed, commands/results, evidence, remaining risks, and next recommended issue without implementing it.

An issue is done only when it satisfies `docs/22_BACKLOG_AND_ACCEPTANCE.md` and `templates/definition-of-done.md`.
