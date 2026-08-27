# Definition of Done

An issue is done only when all applicable items are true:

- Assigned acceptance criteria are satisfied without unrelated scope.
- External inputs are validated; tenant and authorization boundaries are tested.
- Unit tests cover deterministic domain behavior; integration/E2E tests cover changed boundaries.
- Failure, retry, timeout, idempotency and cancellation behavior are explicit where relevant.
- No secret, raw source, arbitrary prompt/context, token, credential or sensitive fixture is logged.
- Migrations are forward-safe and documented; destructive behavior has explicit safeguards.
- AI/ML outputs record exact version/provenance required by the source docs.
- Formal model/RAG/LLM/agent claims include frozen evaluation inputs and raw reproducible artifacts.
- No metric, customer, revenue, scale, accuracy, latency or security claim is invented.
- Format/lint/type/test/build/evaluation commands applicable to the issue pass.
- README/source docs/ADRs/API docs/status/changelog are updated when contracts or evidence change.
- `python eng/sync_master_spec.py` is run after source documentation changes.
- `python eng/sync_master_spec.py --check` passes.
- Codex reports changed files, exact commands/results, evidence, remaining risks and the next suggested issue without implementing it.
- For ML/AI milestones, the Owner Learning Note is produced.
