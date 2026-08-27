# 02 — System Architecture

## Principle

Separate authoritative product state, analysis algorithms, untrusted execution, and optional model serving. Start modular because the difficult parts are data/ML/security—not service count.

## Planes

### Control plane — Django
Organizations/memberships, repositories/installations, snapshots, analysis/evidence lifecycle, organization/repository policy records, audit, web UI/DRF, GitHub adapters.

### Analysis plane — Python packages + Celery
Feature extraction, dependency graph, risk scoring, retrieval/reranking, LLM analysis, LangGraph workflows, evaluation jobs.

### Execution plane — isolated runner (M9+)
Consumes immutable execution plans, creates disposable sandboxes, runs allowlisted commands, returns bounded structured results. It cannot alter product state except through authenticated result submission.

### Model plane — deferred FastAPI
Only when RP-1402 returns `EXTRACT_FASTAPI` under the predeclared measurement gate in docs/20. Otherwise inference remains in workers. No tenancy/business policy belongs in a model service.

## Target modules

```text
apps/web/
  identity organizations repositories changes evidence risk retrieval analysis verification audit
packages/
  domain github_contracts change_intel dataset_core ml_core retrieval_core ai_core
  agent_core execution_contracts observability
workers/
adapters/              # provider implementations and deterministic fakes
apps/model_service/    # deferred
runner/                # M9 separate trust boundary
```

These ten Django app names are canonical for RP-0003. Policy records are owned by `organizations` and `repositories`; policy evaluation belongs in the relevant application service. A standalone `policies` app requires a later assigned issue and documented need.

## Dependency rule

Views/DRF -> application services -> framework-light domain/algorithm ports. Django ORM/GitHub/Redis/S3 are adapters. Core algorithms do not import Django request/template/Celery task objects.

## Storage
- PostgreSQL: authoritative state, evidence metadata, deterministic features, pgvector embeddings, FTS.
- Redis: Celery broker/cache/short coordination; disposable.
- S3-compatible object storage: large immutable diffs/logs/dataset/model artifacts; SeaweedFS is the pinned local Compose implementation under ADR-016.
- MLflow: experiment/model/prompt/evaluation lineage after M13.

## Consistency
- Durable webhook dedupe record before expensive async work.
- A PostgreSQL job record and transactional outbox entry are committed with the triggering state change. A relay publishes outbox entries to Celery/Redis; idempotent workers and a recovery scan handle duplicate delivery or broker loss. Redis never owns job truth.
- Snapshot immutable by repo/PR/base/head/schema.
- Head movement creates a new run; never mutates old evidence.
- Risk/evidence records are versioned/append oriented.
- Execution bound to exact SHAs, artifacts, image digests and plan hash.

## Failure philosophy
Verifier failure reduces confidence and is visible:
- LLM down -> deterministic/ML evidence remains.
- retrieval down -> no historical claims fabricated.
- model unavailable -> explicit baseline fallback or UNKNOWN.
- runner timeout -> timeout/UNKNOWN, never pass.

## Scaling path
1. Django + worker + Postgres/Redis/SeaweedFS Compose.
2. Independent web/worker replicas.
3. separate runner pool.
4. model-service process/GPU pool only if RP-1402 returns `EXTRACT_FASTAPI`.
5. optional Kubernetes when resource scheduling/replica evidence exists.

Kafka is deliberately absent. Introducing it requires a new issue and ADR with a reproducible benchmark showing that the PostgreSQL outbox plus Celery transport cannot meet a stated ordering, replay or throughput requirement.
