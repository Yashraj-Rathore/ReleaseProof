# 38 — M8 Generated-Test Proposal Evaluation

## Decision

M8 accepts the `generated-test-proposal-v1`, `python-fixture-v1` and
`python-fixture-static-v1` contracts for immutable human review and bounded patch export. It does
not accept generated-test execution. RP-0801 threat review, an isolation ADR, an immutable
execution plan and separate execution approval remain mandatory M9 gates.

## Frozen input and provenance

`tests/fixtures/proposals/m8_static_validation_v1.json` is an explicitly synthetic CC0-1.0 suite.
Its SHA-256 is `896c62dce50f34a4f7dfcb60144669487505b243bbf57cc4b643c5b4f7d00793`.
It contains two valid controls and nine invalid adversarial controls: traversal, source
modification, forbidden process import, secret-file read, top-level side effect, invalid syntax,
command injection, dunder introspection and an unknown strict-schema field. It contains no customer
or mined public-repository data.

## Exact configuration

- proposal schema: `generated-test-proposal-v1`;
- adapter: `python-fixture` / `python-fixture-v1`;
- validator: `python-fixture-static-v1`;
- stability repetitions: 5;
- execution, patch application, repository writes and provider calls: disabled.

The adapter permits one new file directly under `tests/generated/`, named `test_*.py`, and the
exact proposed command `python -m pytest -q <file>`. It checks canonical text, new-file patch shape,
Python AST syntax, typed zero-argument test functions, import roots and a narrow capability
allowlist. The evaluator never invokes the proposed command.

## Measurements

The frozen artifact records:

| Measurement | Result |
|---|---:|
| Valid-control acceptance | 1.0 (2/2) |
| Invalid-control rejection | 1.0 (9/9) |
| Invalid false acceptance | 0.0 (0/9) |
| Expected static-check match | 1.0 (11/11) |
| Five-run stability | 1.0 |

The local CPython 3.13.15 Windows run measured the complete static suite 100 times: median
8.3893 ms, p95 13.3381 ms and minimum 7.5647 ms. This excludes database, queue, provider, patch,
test-runner, container and network time. It is not a production latency claim.

The raw artifact is `artifacts/evaluation/m8_test_proposal_eval_v1.json`; its root SHA-256 is
`d4c2c21778b297642a391f2d1ae6d9faa1a1e4fa53ce8d9c149dcda68f131361`.

## Rerun

```text
uv run python -m eng.evaluate_m8_proposals --check
uv run pytest tests/unit/test_test_proposals.py tests/integration/test_generated_test_proposals.py tests/web/test_generated_test_proposal_workflow.py
```

`--check` recomputes stable quality/configuration and separately reports current-machine latency.
Use `--write` only when deliberately revising the frozen fixture/evaluator and review the new raw
cases and root hash.

## Limitations

- All cases and gold judgments are synthetic.
- Exact static rejection does not prove that accepted code is safe or useful.
- AST allowlisting is defense in depth, not a sandbox boundary.
- No generated test, command, patch, repository write, hosted provider or model was executed.
- Human acceptance quality, real-repository portability and regression-killing value are not yet
  measured.
- Sandbox escape resistance, resource isolation and sentinel confidentiality remain unvalidated.
