# ADR-016 — SeaweedFS for Local S3-Compatible Object Storage
**Status:** Accepted

## Context

The original specification named MinIO for local development. MinIO's open-source repository was archived on 2026-04-25 and its final community line is not a maintained security baseline. Keeping it would contradict the requirements for supported dependencies and a production-shaped local stack.

## Decision

Use SeaweedFS 4.44, Apache-2.0, as the local Docker Compose S3-compatible service. Run its documented single-node `weed server -s3` mode only for development, tests and the fictional demo. Pin both the exact tag and resolved OCI manifest digest. Production remains an S3-compatible provider selected by deployment policy; application code depends only on the object-storage port.

ReleaseProof intentionally supports a bounded S3 subset: create/verify configured bucket during bootstrap, put, head, get and delete immutable objects; explicit content length/type; SHA-256 metadata verification; path-style addressing; bounded timeouts; and explicit not-found/unavailable/checksum-mismatch errors. Provider-specific administration, filesystem mounts, public buckets, object-lock claims, replication claims and SeaweedFS APIs are outside the application contract unless a later issue adds and tests them.

Local credentials are non-production, non-empty and supplied through environment/config files excluded from Git. The S3 endpoint is not publicly exposed by default. PostgreSQL retains authoritative artifact metadata and expected checksums; SeaweedFS stores bytes, not product truth.

## Evidence and consequences

- SeaweedFS publishes an actively maintained S3 API and a single-node `weed server -s3` mode: https://github.com/seaweedfs/seaweedfs
- The pinned release is 4.44, published 2026-08-22: https://github.com/seaweedfs/seaweedfs/releases/tag/4.44
- The project is Apache-2.0; production operators still perform dependency, image and license review.
- S3 compatibility is proven by ReleaseProof's own provider contract tests. The project does not claim complete Amazon S3 equivalence.
