# 01 — Product Requirements

## Product statement

ReleaseProof helps engineering teams judge whether a software change is safe enough to merge or release by combining deterministic change analysis, historical evidence, learned risk models, and controlled execution. It returns **SHIP / REVIEW / HOLD / UNKNOWN** with cited evidence; humans retain merge/deploy authority.

## Primary users
- Developer: fast, prioritized evidence.
- Reviewer/Tech Lead: risk areas, missing checks, reproducible findings.
- Engineering Manager: team-level change quality without individual surveillance scoring.
- Platform/SRE/Security: policy, audit, privacy, execution controls.

## Jobs to be done
- Identify what deserves review attention.
- Explain why a change is risky.
- Find similar historical changes/runbooks/incidents.
- Propose missing tests.
- Execute allowed checks safely.
- Compare base vs candidate behavior.
- Separate ML/LLM hypotheses from deterministic/execution facts.
- Provide concise GitHub output and deeper dashboard evidence.
- Learn from outcomes without silently pooling private customer code.

## Invariants
- Advisory only; no autonomous merge/deploy in MVP.
- UNKNOWN is valid when evidence is missing.
- Every score names producer/model/feature version.
- Every LLM claim cites allowed evidence or is labeled hypothesis.
- Organization/repository scope is server-derived.
- Untrusted code never executes on the app host.
- Hosted LLM source transmission is policy-controlled.
- Shared/global training on customer code is off by default.
- Execution failure is not interpreted as pass.
- Synthetic data and proxy labels are explicit.

## MVP
1. One configured GitHub App installation/repository path per MVP deployment and demo. The schema, authorization and query rules remain multi-organization from M2; "one path" limits integration breadth, not tenant-isolation requirements.
2. Signed PR webhook ingestion.
3. Immutable base/head change snapshot.
4. Deterministic features + Python import/blast-radius analysis.
5. Transparent rule-based risk baseline.
6. Repository-scoped historical retrieval.
7. Optional strict-schema hosted LLM analysis plus deterministic fake.
8. GitHub check/status + evidence dashboard.
9. **No arbitrary code execution yet.**

Before RP-0905, each release recommendation uses the latest approved deterministic recommendation-policy version and only the evidence components available at that milestone. Later ML, RAG and LLM outputs cannot silently change that policy. RP-0905 introduces the separately evaluated fusion policy that includes execution and mutation evidence.

## Post-MVP gates
- Classical ML only after provenance/split/leakage controls.
- Test generation only for an explicit fixture adapter first.
- Sandbox only after threat-model approval and isolation tests.
- Differential execution only for configured supported projects.
- PyTorch/HF model only after classical baseline.
- LangGraph only after single-pass LLM path has evaluation.
- FastAPI/vLLM/Kubernetes only after their owning issue's predeclared measurement, hardware, license, privacy and operational-cost gate; explicit deferral is a valid outcome.

## Non-goals
Autonomous merges/deploys; IDE autocomplete; generic code generation; full SAST/DAST replacement; secrets management; incident management; universal build systems; employee ranking; foundation-model pretraining; guaranteed bug prevention.

## Success evidence

Portfolio evidence: deterministic snapshot/features, tenant isolation, measured model metrics on documented proxy labels, retrieval benchmark, sandbox isolation proof, planted regression differential result, bounded agent evaluation, reproducible demo.

Commercial success requires external pilot evidence: useful findings, acceptable false-positive burden, installation retention, cost, and willingness to pay. Technical benchmarks do not prove business value.
