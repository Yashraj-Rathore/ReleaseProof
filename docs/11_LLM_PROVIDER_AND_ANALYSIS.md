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

## M7 implementation decision

M7 implements `RP-0601..RP-0606` without LangChain or an agent framework. The framework-light
contract, policy, prompt/schema loader and evaluator live under `packages/ai_core`; adapters remain
under `adapters/llm`; Django resolves tenant policy/context and appends safe evidence. The default
test/demo provider is `deterministic-evidence-synthesizer-v1` and performs no network access.

The hosted adapter pins `openai==3.6.0` and the immutable model snapshot
`gpt-5.4-mini-2026-03-17`. It uses the Responses API with strict JSON Schema, `store=false`, no
tools, disabled truncation, an explicit maximum output, default service tier, separate SDK
connect/read timeouts and SDK retries disabled in favor of the request's bounded retry policy.
Pricing is injected as versioned reviewed configuration; no mutable or invented production price
is hard-coded. Provider configuration must state training-use review, retention mode/duration and
region. `store=false` is recorded only as response-storage disabled and is never called zero
retention.

Hosted routing additionally requires the organization's kill switch, an immutable effective
policy, exact provider/model/content/region compatibility, current reviewed terms and size/token/
cost limits. `local_only` never calls a hosted provider. `hosted_redacted` applies the versioned
deterministic defense-in-depth redactor before size/token checks. Any denial or provider/schema
failure yields missing LLM evidence with a stable status; deterministic and retrieval evidence
remain intact.

The frozen M7 evaluation is documented in `36_M7_LLM_EVALUATION.md`. It validates the deterministic
contract harness only. Hosted-model usefulness, provider latency/cost, contractual retention and
regional behavior are not yet measured because no hosted provider was called.
