# 42 — M9 Owner Learning Note

## 1. Concept implemented

M9 implements capability-constrained execution as a separate trust boundary: immutable signed
plans, exact human approval, a disposable fixture container, strict result evidence and append-only
idempotent persistence.

## 2. Why ReleaseProof uses it

Static checks cannot make generated code trustworthy. Separating content acceptance from exact
execution authorization and isolating the runner prevents a reviewer action or stale hash from
silently granting broader code, image, network, mount or resource permissions.

## 3. Algorithm/data assumptions

The only repository is a known synthetic fixture with a frozen tree hash. The generated change is
one M8-validated file and exact pytest argv. HMAC authenticates boundary messages but assumes safe
runtime key distribution. Docker shares a kernel, so rootless/dedicated-host controls reduce risk
without proving VM-equivalent hostile-code isolation.

## 4. Key code paths

- `packages/execution_contracts/`: strict plan/result/input schemas, hashes and signatures;
- `apps/web/verification/execution_services.py`: current-head plan, approval and result rules;
- `runner/docker_cli.py`: host validation, Docker hardening, timeout and cleanup;
- `runner/fixture_image/entrypoint.py`: safe patch materialization, probes and bounded test capture;
- `tests/sandbox/test_fixture_runner.py`: live isolation/resource/cleanup sentinels;
- `eng/evaluate_m9_runner.py`: frozen non-live policy regression evidence.

## 5. Exact experiment/test to rerun

Run the commands in docs/41. Also run the unit/integration/web tests for execution contracts,
workflow and CSRF/tenancy before interpreting live sandbox output.

## 6. Likely interview question

**Why is Docker not enough to claim arbitrary hostile-code isolation?**

Containers share the host kernel; a runtime or kernel escape can cross the boundary. ReleaseProof
therefore narrows M9 to a frozen fictional fixture on a dedicated rootless disposable host, layers
seccomp/LSM/capability/network/resource controls, and keeps external repositories disabled until a
stronger backend receives its own threat review and accepted ADR.
