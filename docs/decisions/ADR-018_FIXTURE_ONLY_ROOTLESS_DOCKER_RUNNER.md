# ADR-018 — Fixture-only rootless Docker runner

- **Status:** Accepted
- **Date:** 2026-09-02
- **Deciders:** ReleaseProof owner/security review
- **Issues:** RP-0801..RP-0805

## Context

M9 needs execution evidence, but a container shares a kernel with its host and is not a VM-equivalent
boundary. The Django/Celery/control hosts must never execute repository code or receive a Docker
socket. Ordinary shared-host Docker is therefore not approved for arbitrary hostile customer code.

## Decision

The M9 product runner supports only the exact, source-controlled fictional Python fixture and a
statically accepted M8 add-only test. Its durable host is a single-purpose, disposable Linux host
running Docker Engine in rootless mode with cgroups v2, the built-in seccomp profile, and an
enforcing host LSM. The runner host is outside the application/Celery trust boundary.

Every plan pins the fixture tree, checkout, proposal/input, runner image digest, argv, constant
environment, no-network/no-mount policy, resources, artifacts and plan hash. Control-plane and
runner messages are HMAC-authenticated. The candidate container is non-root, read-only, capability
free, `no-new-privileges`, network `none`, and limited by CPU, memory, PIDs, tmpfs, wall time and
output. It receives no host path, Docker socket, SSH agent, cloud/GitHub/LLM/customer secret, or
ambient host environment. Cleanup is mandatory and its result is evidence.

GitHub Actions may run the same source-controlled sentinel probes on its disposable rootful Linux
worker only under the explicit `ephemeral-ci-fixture-v1` profile. That proves command-line controls
and observed fixture behavior; it does not approve rootful CI as the durable product backend.

Arbitrary external repository execution remains disabled. Enabling it requires a new threat review
and ADR selecting a stronger boundary such as a microVM/user-space-kernel backend, plus escape
testing and operations evidence. A plan/profile flag cannot widen the M9 scope.

## Consequences

- M9 provides honest execution evidence for a narrow fictional fixture without making a universal
  sandbox claim.
- A dedicated runner operator must verify rootless Docker, seccomp, LSM and host disposal before
  accepting work.
- Application services persist plans/approvals/results but never import or invoke runner code.
- Kernel/runtime compromise of a general hostile workload remains High; disabling that workload
  makes it outside the accepted M9 boundary rather than silently accepting the risk.
