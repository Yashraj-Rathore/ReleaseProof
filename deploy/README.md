# Local infrastructure

Prompt 1 supplies the production-shaped local data services: PostgreSQL/pgvector, Redis and
SeaweedFS. M13 adds a dedicated MLflow tracking-server image that uses PostgreSQL and proxied
SeaweedFS artifacts. Web/worker production images remain owned by M15. Kubernetes remains deferred.

The Compose image references include both an exact tag and the multi-architecture OCI index
digest resolved on 2026-08-27. Generate the Git-ignored SeaweedFS `s3.local.json` from `.env` with
`uv run --env-file .env python -m eng.configure_local`; credentials must never be reused outside
local development. Only loopback host ports are published.

Generate the local config before `docker compose up -d --wait`. Then run
`uv run --env-file .env python -m eng.bootstrap_object_store` to idempotently create/verify the
configured bucket, followed by `uv run --env-file .env python -m eng.smoke_mlflow` to verify the
exact server/client version and register the safe M13 records. MLflow is published only on the
loopback `MLFLOW_PORT`; this local unauthenticated profile must not be exposed to a network.
`docker compose stop` and `docker compose down` preserve named volumes.
Only `docker compose down --volumes` is the explicit destructive reset; it permanently removes
local database, Redis, and SeaweedFS data.

No real cloud credentials or production identifiers belong in this repository.
