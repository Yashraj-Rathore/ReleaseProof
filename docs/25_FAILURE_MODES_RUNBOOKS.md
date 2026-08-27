# 25 — Failure Modes and Runbooks

- **Webhook bad signature:** reject, no trusted parse.
- **Duplicate delivery:** idempotent success, no duplicate snapshot/run.
- **GitHub API/rate limit:** retain durable receipt, bounded backoff, visible pending/failure.
- **Postgres down:** readiness fails; never claim webhook accepted without durable commit.
- **Redis down:** authoritative evidence remains in Postgres; async work pauses/retries safely.
- **Outbox relay/Redis loss:** committed PostgreSQL job/outbox rows remain pending; the recovery scan republishes with the same idempotency key and duplicate task delivery is harmless.
- **Object store down/corrupt response:** retain authoritative metadata and expected checksum in PostgreSQL, reject mismatched content, mark the component unavailable and never fabricate artifact-backed evidence.
- **LLM down/invalid:** preserve deterministic/ML/RAG, record failure, REVIEW/UNKNOWN possible.
- **Model artifact missing/mismatch:** reject score; explicit baseline fallback/UNKNOWN.
- **RAG stale/unavailable:** no fabricated history; rebuild versioned index.
- **Runner down:** execution UNKNOWN, never pass.
- **Runner isolation failure:** disable runner globally and block external execution until security review.
- **Candidate timeout/kill:** explicit result; compare base under same limits where useful.
- **MLflow down:** pinned approved inference may continue if designed; promotion/training metadata pauses.
- **Budget exceeded:** stop further LLM/agent calls and preserve gathered evidence.
- **Retention delete:** dry-run first, tenant-scoped, idempotent, backup/recovery considerations documented.
