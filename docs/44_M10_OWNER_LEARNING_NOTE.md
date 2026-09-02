# 44 — M10 Owner Learning Note

## 1. Concept implemented

M10 implements controlled base-versus-candidate differential replay, selected semantic comparison,
a bounded mutation-testing slice and deterministic recommendation fusion. Every executable input is
checksum/version bound, and every persisted plan/result/decision is immutable and tenant scoped.

## 2. Why it is used here

A risk score says where to investigate; differential replay asks whether the candidate demonstrably
behaves differently under the same workload. Mutation testing checks whether the selected tests can
detect small planted faults. Fusion makes the final advisory outcome predictable when those facts
agree, disagree or are missing.

## 3. Algorithm and data assumptions

The first adapter assumes one synthetic Python fixture and a finite image-bundled revision/mutation
set. The comparator considers test outcome, selected HTTP status/schema/body, state and events.
Exactly two known nondeterministic paths are masked. Timing is descriptive only. The mutation score
is killed divided by non-inconclusive mutants; two mutants are far too small for a quality claim.

Fusion precedence is deterministic HOLD, then UNKNOWN for any unavailable mandatory component,
then REVIEW conditions, then advisory SHIP. An LLM suggestion is an input for transparency but is
never decisive. A same-model critic would not change this ordering.

## 4. Key code paths

- `packages/execution_contracts/differential.py`: strict contracts, hashes and comparison.
- `runner/fixture_image/differential_entrypoint.py`: in-sandbox parity replay and mutations.
- `runner/docker_cli.py`: signed host boundary, image labels, limits and cleanup.
- `packages/recommendation_core/policy.py`: deterministic fusion and immutable decision contract.
- `apps/web/verification/differential_services.py`: tenant/evidence lineage and persistence.
- `apps/web/verification/migrations/0007_differential_integrity.py`: composite and append-only DB controls.

## 5. Exact experiment/test to rerun

```text
uv run python -m eng.evaluate_m10_differential --check
uv run pytest tests/unit/test_differential_contracts.py tests/unit/test_recommendation_policy.py tests/integration/test_differential_workflow.py
RUN_SANDBOX_INTEGRATION=1 uv run pytest -m sandbox tests/sandbox
```

The sandbox command requires the documented image build and a disposable Linux Docker host. The
normal evaluator is network-free and does not execute fixture code.

## 6. Likely interview question

**Why is a candidate difference or surviving mutation not automatically a HOLD?**

A difference may be intended, and a survived mutant only indicates that this workload did not
distinguish it. ReleaseProof preserves attributable facts and applies an explicit versioned policy:
known deterministic regression evidence can HOLD, incomplete evidence becomes UNKNOWN, and weak but
non-definitive coverage becomes REVIEW. A human still decides whether to merge or deploy.
