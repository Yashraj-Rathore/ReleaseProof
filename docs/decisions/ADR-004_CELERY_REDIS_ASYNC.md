# ADR-004 — Celery + Redis Transport with PostgreSQL-Durable Jobs
**Status:** Accepted

Long-running ingestion, feature extraction, embedding, LLM, verification, and evaluation work is queued. HTTP requests do not synchronously wait on expensive AI or sandbox jobs.

PostgreSQL owns the job lifecycle and a transactional outbox entry committed with the state change that requests work. An outbox relay publishes to Celery through Redis. A recovery scan republishes pending/stale outbox rows after relay or broker failure. Workers use the PostgreSQL job/idempotency key, tolerate duplicate delivery, and record bounded attempts and terminal outcomes. Redis/Celery transport loss cannot erase an accepted webhook, requested analysis, or authoritative result; Celery result storage is not product state.
