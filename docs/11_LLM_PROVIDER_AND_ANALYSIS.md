# 11 — LLM Provider and Evidence Analysis

## Purpose
LLMs synthesize hypotheses and proposed checks from deterministic, ML and retrieved evidence. They never override deterministic policy or failing execution evidence.

## Provider contract
`AnalysisLLMProvider.analyze_change(request) -> AnalysisSuggestionV1`

Required adapters:
- deterministic fake from M1;
- OpenAI hosted adapter in M7;
- second hosted or local adapter only through an assigned issue that reuses the contract and passes the privacy/schema/evaluation suite;
- optional Ollama/local OpenAI-compatible path;
- vLLM only when M15 evidence warrants local generative serving.

## Strict schema
Result contains:
- concise summary;
- risk hypotheses with severity/confidence;
- allowed evidence references;
- suggested tests/checks;
- missing information;
- uncertainty.
Invalid JSON/schema/evidence references are rejected, not massaged into trusted output.

## Prompt/model versioning
Every evidence item records prompt semantic version + content hash + provider/model ID + adapter version.

## Privacy routing
Organization policies:
1. `local_only` — no source to hosted providers.
2. `hosted_redacted` — bounded/redacted content.
3. `hosted_allowed` — configured hosted provider may receive allowed content.
Default is conservative.

The versioned policy snapshot also records provider and model allowlists, allowed content classes, maximum transmitted bytes/tokens, redaction version, provider training/use statement review date, provider retention mode/duration, region/residency constraints where applicable, whether provider-side response storage is disabled, and the approving organization role. Unknown or incompatible provider retention/training terms force `local_only`; `store=false` or redaction alone is never represented as zero retention or permission.

## Reliability/cost
Explicit connect/read timeouts, bounded transient retry, request/run token and cost caps, cancellation, backoff/circuit behavior, fake default for test/demo.

## Prompt injection
Repository content is hostile data. It may contain instructions but cannot alter system policy, tenant scope, tool allowlists, runner permissions, secrets, or budgets. Server-side authorization remains authoritative.

## Evaluation
Frozen cases measure:
- schema validity;
- evidence citation correctness;
- unsupported-claim rate;
- suggested-check usefulness under a fixed rubric;
- prompt-injection resilience;
- missing/conflicting evidence handling;
- latency/tokens/cost.
LLM-as-judge can supplement but not replace deterministic assertions/human-reviewed gold cases.
