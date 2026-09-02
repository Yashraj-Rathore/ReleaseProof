# 41 — M9 Runner Evaluation

## Evidence layers

The committed CC0 synthetic artifact verifies the frozen fixture tree, strict hashes/signatures,
image/argv/environment policy and every generated Docker hardening/resource argument without
starting a container. `python -m eng.evaluate_m9_runner --check` must reproduce it exactly.

The separate `sandbox` pytest marker is the live evidence layer. On a disposable Linux CI worker it
builds the digest-pinned fictional-fixture image and proves non-root identity, zero effective
capabilities, no-new-privileges, read-only root, absent host mount/socket/parent secret, loopback-only
network, blocked metadata, exact cgroup CPU/memory/PID ceilings, bounded tmpfs, timeout/kill,
bounded output and post-run container cleanup. A tampered signature is rejected before create.

The live CI profile is intentionally rootful because the hosted worker is ephemeral. Passing it
does not qualify that host for product traffic; the durable profile separately fails closed unless
Docker reports rootless mode.

## Decision and limitations

The fixture contract/policy may be enabled only after exact human execution approval. Arbitrary
external repositories remain disabled. All examples are synthetic; no customer code, dependency
download at runtime, hosted model or paid API is involved. No benchmark or sentinel proves absence
of every container/kernel escape. Runner throughput, queue transport and representative cost are
not yet measured.

## Rerun

```text
uv run python -m eng.evaluate_m9_runner --check
docker build -f runner/fixture_image/Dockerfile -t releaseproof-fixture-runner:m9 .
RUN_SANDBOX_INTEGRATION=1 uv run pytest -m sandbox tests/sandbox
```
