# ADR-001 — Modular Monolith First
**Status:** Accepted

ReleaseProof begins as one Django application with explicit module boundaries plus Celery workers. Do not split business modules into network services solely to resemble a distributed system. A service may be extracted only when a measured scaling, security, dependency-isolation, or deployment requirement makes the boundary useful. The sandbox runner is a separate trust boundary and is not evidence that every module should be a microservice.
