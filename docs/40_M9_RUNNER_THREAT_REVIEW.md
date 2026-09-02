# 40 — M9 Runner Threat Review and Signoff

## Scope and signoff

This review gates RP-0801. The accepted scope is one exact tree hash of the in-repository fictional
fixture plus one M8-valid add-only test. The durable backend and host assumptions are fixed by
ADR-018. External/customer repositories, arbitrary commands, dependency installation and service
containers are denied. Within that restricted scope there is no unmitigated Critical/High finding;
the High shared-kernel risk for arbitrary hostile repositories is excluded and remains a hard stop.

## Trust boundaries

1. The Django control plane creates and persists immutable plans, approvals and safe results. It
   never has a Docker socket and never executes repository code.
2. An authenticated plan/input crosses to a dedicated, disposable Linux runner host. Transport and
   key distribution are deployment responsibilities; signing keys are referenced at runtime and
   never persisted in product rows or logs.
3. The runner validates exact schema/hash/signature, host profile, fixture/input/image identity and
   Docker policy before creating a candidate container.
4. Container output is untrusted. Only a strict bounded result is accepted and persisted.

## Ranked attack paths and disposition

| Severity | Attack path | Required control/evidence | Disposition |
|---|---|---|---|
| Critical | control-plane host executes candidate or exposes Docker socket | architectural import test; runner is a separate package/deployable; no control-plane runner call | mitigated |
| Critical | cloud/GitHub/LLM/customer credential reaches candidate | constant env allowlist, no mounts/socket/SSH agent, live parent-secret sentinel | mitigated |
| High | container/kernel/runtime escape | dedicated rootless disposable host, default seccomp, enforcing LSM, no capabilities/privilege; source-controlled fixture scope | mitigated for M9 scope; external code disabled |
| High | forged/tampered plan widens image/command/network/mounts/resources | strict duplicate/extra-field rejection, immutable hash and HMAC, fixed image namespace/argv/network/mount/env policies | mitigated |
| High | cross-tenant approval/result binding | server-derived organization scope, exact snapshot/proposal/plan hashes, composite database FKs/triggers, IDOR tests | mitigated |
| High | stale head/proposal executes under old approval | current-head/lifecycle check; changes make plan non-executable; late result is retained as stale evidence | mitigated |
| High | network exfiltration/metadata access | Docker network `none`; loopback-only/metadata sentinel; no install phase at runtime | mitigated |
| High | denial through CPU/memory/PID/disk/time/output exhaustion | cgroup limits, bounded tmpfs, inner/outer timeout+kill, bounded Docker logs and result excerpts | mitigated |
| Medium | image/tag substitution | `repository@sha256` contract and local exact image-ID inspection; no mutable runtime tag | mitigated |
| Medium | malicious output/schema/log injection | bounded UTF-8 replacement, full byte hash/size, strict JSON result parser, no raw output in audits | mitigated |
| Medium | abandoned containers after failure/retry | random names, ownership label, `rm --force` in `finally`, cleanup fact and live enumeration | mitigated |
| Medium | duplicate delivery creates conflicting evidence | organization idempotency key plus plan/attempt uniqueness; mismatched duplicate rejects | mitigated |

## Kernel and host assumptions

- Linux only; rootless Docker is mandatory for the durable profile.
- cgroups v2 must enforce memory, CPU and PID limits.
- Docker's built-in seccomp profile and an enforcing AppArmor/SELinux policy must remain enabled.
- The runner host contains no production/cloud credentials, customer data, repository write token,
  SSH agent or unrelated workloads and can be destroyed after credible compromise.
- Docker Engine/runtime/kernel/security updates are an operator precondition. Containers are not
  described as VM-equivalent isolation.

## Secrets, network, filesystem, quotas and cleanup

The only environment is four fixed non-secret Python/locale settings. Network and host binds are
empty. The root filesystem and fixture image are read-only; `/workspace` and `/tmp` are size-bounded
tmpfs mounts. Numeric UID/GID 65532, all capabilities dropped, `no-new-privileges`, no privilege,
no host namespace and no Docker socket are required. The v1 ceilings are 0.5 CPU, 256 MiB memory,
64 PIDs, 64 MiB workspace, 16 MiB `/tmp`, 60 seconds maximum wall time, 64 KiB per persisted output
excerpt and one bounded Docker log file. The host force-removes the container in `finally`; cleanup
failure cannot be represented as successful cleanup.

## Residual risk and stop conditions

Supply-chain compromise of the pinned image/build inputs, a kernel/runtime escape, or incorrect
runner-host provisioning remains possible. Any missing rootless/seccomp/LSM/cgroup fact on the
durable host, fixture hash mismatch, signature failure, policy mismatch, sentinel failure or
credible escape report stops execution and produces no positive evidence. External hostile-code
execution remains disabled until a later accepted isolation ADR.

## Approval record

ADR-018 is accepted for this scope on 2026-09-02. This signoff approves implementation and
evaluation of RP-0802..RP-0805 only; it is not a production-readiness or arbitrary-code claim.
