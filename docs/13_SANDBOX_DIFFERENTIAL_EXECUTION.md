# 13 — Generated Tests, Sandbox and Differential Execution

## Security premise
Repository code is hostile. Never execute it on Django/Celery/control hosts.

## Generated test lifecycle
Evidence -> LLM/adapter creates immutable draft revision -> static path/size/capability validation -> human accepts for export or rejects -> M9+ separately authorizes execution of an exact revision -> immutable execution plan -> disposable sandbox -> result evidence. Proposal acceptance never enqueues execution and a proposal is never automatically committed to a customer repository.

Editing creates a new draft/hash and supersedes the prior revision. Execution authorization requires repository execution to be enabled and a Reviewer/Admin to approve the exact snapshot, proposal hash, command allowlist, runner image digest, resource/network policy and plan hash. Head movement, proposal edit or plan change invalidates authorization. Every transition is append-only audited; unattended policy approval is outside the initial runner scope.

## First supported adapter
A fictional Python Django/FastAPI fixture repository with deliberately planted auth, transaction and latency regressions. This proves the pipeline without claiming universal build-system support.

External repo execution later requires explicit configuration: image/toolchain, install/build/test commands, service dependencies, network policy, resource/time/output budgets.

### M8 implemented boundary

`python-fixture-v1` constructs a strict proposal for one new Python file directly under
`tests/generated/`. It accepts only a canonical add-only patch and the exact focused pytest command.
Validation uses inert text checks and `ast.parse`; it rejects traversal, source modification,
syntax/shape failures, unknown imports, dunder access and file/process/network-like capabilities.
This allowlist is defense in depth, not an isolation boundary.

Draft, review, edit and export paths never invoke a shell, subprocess, Python import, patch tool,
Celery task, runner or repository writer. Acceptance means only `accepted_for_export`. The command
is displayed as untrusted proposed text and is not executed. The committed M8 adversarial fixture
and evaluator likewise perform static validation only. M9 remains blocked on RP-0801 and an
accepted isolation ADR before any runner implementation.

## Isolation requirements
- separate runner trust boundary for real untrusted execution;
- non-root;
- no privileged mode;
- no host Docker socket;
- no production/cloud/GitHub/LLM credentials;
- no SSH agent;
- network `none` by default;
- ephemeral work volumes;
- read-only root FS where feasible;
- CPU/memory/PID/wall-time/output limits;
- pinned image digest;
- no host network/mounts.

Containers reduce risk but are not described as VM-equivalent isolation. Consider gVisor/Firecracker/Kata later after threat/ops review.

RP-0801 must produce an accepted ADR selecting the actual local isolation backend and its host assumptions before runner code begins. If the threat review cannot justify that backend for hostile external repositories, M9 remains restricted to the fictional fixture or stops; ordinary shared-host Docker is not silently claimed as a universal security boundary.

## Sentinel tests
Control environment exposes fake sentinel secrets that candidate must be unable to read via env, mounts, metadata endpoints, socket, or network.

## Differential verification
Run same bounded workload against exact base and candidate with same toolchain/policy. Compare:
- test outcomes;
- selected HTTP status/schema/semantics;
- bounded DB state summaries;
- selected events;
- exceptions;
- repeated latency/resource observations only with measurement caveats.
A difference is evidence, not automatically a defect.

## Mutation testing
Controlled mutations only on fixture/explicitly configured paths initially. Mutation survival means test weakness may exist; it is not proof of a production bug.

## Failure semantics
Runner unavailable/timeout/install failure => UNKNOWN/REVIEW evidence, never pass. If base also fails, candidate cannot be blamed solely by that check.
