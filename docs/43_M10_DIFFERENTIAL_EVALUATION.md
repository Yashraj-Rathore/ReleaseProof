# 43 — M10 Differential, Mutation and Fusion Evaluation

## Scope and configuration

This evidence covers `RP-0901..RP-0905` for the source-controlled fictional fixture only. It does
not enable or evaluate arbitrary external/customer repository execution. The executable base and
finite overlays are frozen by bundle SHA-256
`8e3554c97d41207213554f092e2bcb439560164ae0fcb744c5b56e6adf81f87e` and copied into the existing
digest-selected M9 image. Plan, result, workload, mask, mutation and recommendation versions are:

- `releaseproof.differential-plan.v1`;
- `releaseproof.differential-result.v1`;
- `releaseproof.fixture-workload.v1`;
- `releaseproof.fixture-mask.v1`;
- `releaseproof.fixture-mutations.v1`;
- `recommendation-fusion-v1`.

Base/candidate parity means the exact same image, Python environment, resource/network/mount
policy, generated test and handler-probe commands. The base/candidate revision checksums and M9
plan/approval/proposal/input hashes are part of the signed plan.

## Frozen deterministic results

The CC0-1.0 fixture in `tests/fixtures/execution/m10_differential_cases_v1.json` is synthetic and
authored in-repository. Its four differential cases all pass:

| Case | Expected/actual outcome | Selected differences |
|---|---|---|
| identical | `no_difference` | none |
| planted tax regression | `difference` | `tests.outcome`, `http.body` |
| candidate probe timeout | `unknown` | none attributed |
| base failure | `base_failed` | none attributed to candidate |

Both explicit mask controls pass: `http.headers.x-request-id` and `state.updated_at` do not create
a difference. Status, schema, body, selected non-masked state and selected events remain comparable.
Latency is retained as descriptive evidence and is not a threshold in this version.

The bounded mutation slice has two controlled source overlays. The generated test kills the
forced-tax mutation and the removed-negative-guard mutation survives: 1 killed / 2 eligible = 50%.
This validates mutation accounting. Two hand-authored operators are not representative mutation
coverage, and survival suggests a possible test gap rather than proving a production defect.

All four frozen fusion cases pass:

| Case | Expected/actual recommendation |
|---|---|
| all mandatory evidence clear | `SHIP` |
| mandatory execution evidence missing | `UNKNOWN` |
| deterministic differential HOLD + LLM SHIP | `HOLD` |
| mutation score below 50% | `REVIEW` |

Every output has `advisory_only=true` and `auto_merge=false`.

## Evidence boundary

`artifacts/evaluation/m10_differential_eval_v1.json` is a deterministic contract/policy artifact;
it does not execute a container. The sandbox-marked test separately builds the pinned fixture image
on disposable Linux CI and executes identical, planted-regression and timeout variants while
rechecking the M9 isolation flags and cleanup. That live result is not claimed until the workflow
for the exact pushed revision succeeds.

The HTTP observation invokes a synthetic handler contract in-process and opens no socket. It proves
selected comparison semantics, not Django/FastAPI server compatibility. No model was trained or
downloaded, no customer/public data was acquired, and no hosted/paid provider was called.

## Reproduce

```text
uv run python -m eng.evaluate_m10_differential --check
uv run pytest tests/unit/test_differential_contracts.py tests/unit/test_recommendation_policy.py tests/integration/test_differential_workflow.py
docker build -f runner/fixture_image/Dockerfile -t releaseproof-fixture-runner:m9 .
RUN_SANDBOX_INTEGRATION=1 uv run pytest -m sandbox tests/sandbox
```
