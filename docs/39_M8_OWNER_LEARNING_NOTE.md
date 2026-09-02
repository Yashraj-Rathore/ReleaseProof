# 39 — M8 Owner Learning Note

## 1. Concept implemented

M8 implements generated tests as immutable, evidence-linked proposals rather than executable
instructions. A controlled adapter constructs a strict proposal for one new Python fixture test,
and static validation returns attributable checks. Human lifecycle events record draft,
accepted-for-export, rejected and superseded state without mutating proposal content.

## 2. Why ReleaseProof uses it

LLM-generated code is untrusted, but a reviewer still needs a reproducible artifact to inspect.
Hashing a strict proposal and separating content revision, review/export acceptance and later
execution authorization prevents an ambiguous “approved” flag from silently becoming permission
to run or commit different code.

## 3. Algorithm and data assumptions

The first adapter assumes a deliberately narrow synthetic Python fixture: one add-only
`tests/generated/test_*.py` patch, one exact pytest command, import roots `fixture_app`/`pytest`,
typed zero-argument test functions and no obvious file/process/network/dunder capabilities. The
source LLM evidence is already immutable, tenant-scoped and completed; citations must be a subset
of its references. Static success is not a safety or usefulness proof. The evaluation data is CC0,
synthetic and cannot support customer-quality claims.

## 4. Key code paths

- `packages/ai_core/proposals.py`: strict schema, generation metadata and stable proposal hash;
- `adapters/test_generation/python_fixture.py`: controlled proposal builder and inert static checks;
- `apps/web/verification/models.py`: immutable revisions and append-only lifecycle events;
- `apps/web/verification/services.py`: source binding, review transitions, edits and bounded export;
- `apps/web/verification/api.py`, `views.py` and template: tenant/role/CSRF human workflow;
- `eng/evaluate_m8_proposals.py`: frozen adversarial evaluation without code execution.

## 5. Exact experiment/test to rerun

```text
uv run python -m eng.evaluate_m8_proposals --check
uv run pytest tests/unit/test_test_proposals.py tests/integration/test_generated_test_proposals.py tests/web/test_generated_test_proposal_workflow.py
```

Inspect `artifacts/evaluation/m8_test_proposal_eval_v1.json` for every observed static-check code,
proposal/content hash and the explicit `execution_enabled=false` decision.

## 6. Likely interview question

**Why does accepting a generated test not authorize execution?**

Because content review and hostile-code execution have different risks and evidence. M8 acceptance
is bound to an immutable proposal hash and permits only export. M9 must separately bind the exact
snapshot, proposal and execution-plan hashes to a human approval after isolation threat review;
any content/plan change invalidates that authorization.
