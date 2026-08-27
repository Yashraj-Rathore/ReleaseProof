# 05 — GitHub Integration

## Model
Use a GitHub App for repository permissions/webhooks. Human web identity is independent. No personal token is the core repository authorization mechanism.

## Permission intent
Prompt 0/M2 verifies current official permission names. Initial intent:
- metadata: read
- pull requests: read
- contents: read only if analysis requires it
- checks/status: write only for ReleaseProof output
- issues/actions/workflows: deferred unless a specific feature needs them
- never code/admin write for MVP

## Initial events
`pull_request` opened/synchronize/reopened plus installation lifecycle and repository added/removed events. CI/workflow evidence is later.

## Secure ingestion
1. Bound raw body.
2. Verify HMAC signature.
3. Validate event/action.
4. Dedupe GitHub delivery ID.
5. Resolve installation -> org server-side.
6. Obtain short-lived installation token.
7. Fetch exact base/head metadata/diff as inert data.
8. Atomically create immutable snapshot, authoritative analysis job and transactional outbox entry.
9. Relay the outbox entry to Celery/Redis; recovery republishes pending work with the same idempotency key.

## Source handling
Do not clone and execute repository code on web/worker hosts. Static analysis treats content as inert bytes/text. Execution content enters the runner only after M9 policy/security gates.

## GitHub output
One concise check/status, not comment spam. Include recommendation, component availability, model/baseline identifier and dashboard link. Stale run cannot overwrite the latest head conclusion.

## Demo
Provide signed fixture webhook payloads and a deterministic fake GitHub adapter. Recruiter demo requires no live GitHub installation.
