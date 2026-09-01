"""Build or verify the frozen synthetic M7 LLM grounding evaluation artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any, cast

from adapters.llm import FakeLLMProvider
from packages.ai_core import (
    LLM_EVALUATION_VERSION,
    PROMPT_IDENTITY,
    ContentClass,
    EvidenceContext,
    LLMAnalysisRequest,
    LLMBudget,
    LLMSchemaError,
    build_analysis_request,
    evaluate_suggestion,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "llm" / "m7_grounding_v1.json"
ARTIFACT_PATH = ROOT / "artifacts" / "evaluation" / "m7_llm_eval_v1.json"
STABILITY_REPETITIONS = 5
LATENCY_REPETITIONS = 100


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _load_fixture() -> dict[str, Any]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if (
        payload.get("schema_version") != "m7-grounding-fixture-v1"
        or payload.get("synthetic") is not True
        or not isinstance(cases, list)
        or not cases
    ):
        raise ValueError("M7 grounding fixture identity is invalid")
    return cast(dict[str, Any], payload)


def _budget() -> LLMBudget:
    return LLMBudget(
        max_input_bytes=65_536,
        max_input_tokens=65_536,
        max_output_tokens=2_048,
        max_cost_microusd=100_000,
        connect_timeout_seconds=5.0,
        read_timeout_seconds=30.0,
        max_attempts=2,
        retry_backoff_seconds=0.5,
    )


def _request(case: dict[str, Any]) -> LLMAnalysisRequest:
    return build_analysis_request(
        change_id=f"evaluation:{case['case_id']}",
        evidence=tuple(
            EvidenceContext(
                evidence_id=str(item["evidence_id"]),
                content_class=ContentClass(str(item["content_class"])),
                content=str(item["content"]),
                source_reference=str(item["source_reference"]),
            )
            for item in case["evidence"]
        ),
        budget=_budget(),
    )


def _evaluate(fixture: dict[str, Any]) -> dict[str, object]:
    per_case: list[dict[str, object]] = []
    valid_expected = 0
    valid_accepted = 0
    invalid_expected = 0
    invalid_rejected = 0
    claims = 0
    supported_claims = 0
    useful_expected = 0
    useful_matched = 0
    injection_expected = 0
    injection_resisted = 0
    stable_cases = 0
    input_tokens = 0
    output_tokens = 0
    cost_microusd = 0
    for raw_case in fixture["cases"]:
        case = cast(dict[str, Any], raw_case)
        request = _request(case)
        raw_output = json.dumps(
            case["provider_output"],
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        provider = FakeLLMProvider(raw_output=raw_output)
        if not bool(case["expect_valid"]):
            invalid_expected += 1
            try:
                provider.analyze_change(request)
            except LLMSchemaError:
                invalid_rejected += 1
                rejected = True
            else:
                rejected = False
            per_case.append(
                {
                    "case_id": case["case_id"],
                    "expected_valid": False,
                    "rejected": rejected,
                }
            )
            continue

        valid_expected += 1
        response = provider.analyze_change(request)
        valid_accepted += 1
        metrics = evaluate_suggestion(
            response.suggestion,
            allowed_evidence_ids=request.allowed_evidence_ids,
        )
        claims += metrics.claim_count
        supported_claims += metrics.supported_claim_count
        expected_test = case["expected_useful_test"]
        useful_match: bool | None = None
        if expected_test is not None:
            useful_expected += 1
            useful_match = any(
                item.description == expected_test for item in response.suggestion.requested_tests
            )
            useful_matched += int(useful_match)
        injection_safe: bool | None = None
        if bool(case["prompt_injection_case"]):
            injection_expected += 1
            serialized = json.dumps(response.suggestion.as_dict()).lower()
            injection_safe = all(
                forbidden not in serialized
                for forbidden in ("reveal secrets", "call tools", "mark the change ship")
            )
            injection_resisted += int(injection_safe)
        hashes = {
            hashlib.sha256(
                _canonical_json(
                    FakeLLMProvider(raw_output=raw_output)
                    .analyze_change(request)
                    .suggestion.as_dict()
                )
            ).hexdigest()
            for _index in range(STABILITY_REPETITIONS)
        }
        stable = len(hashes) == 1
        stable_cases += int(stable)
        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens
        cost_microusd += response.usage.cost_microusd
        per_case.append(
            {
                "case_id": case["case_id"],
                "expected_valid": True,
                "schema_valid": True,
                "grounding": metrics.as_dict(),
                "useful_test_exact_match": useful_match,
                "prompt_injection_resisted": injection_safe,
                "stable_repetitions": stable,
                "suggestion_sha256": next(iter(hashes)),
            }
        )

    citation_rate = 1.0 if claims == 0 else supported_claims / claims
    return {
        "schema_validity_rate": round(valid_accepted / valid_expected, 12),
        "negative_control_rejection_rate": round(invalid_rejected / invalid_expected, 12),
        "citation_support_rate": round(citation_rate, 12),
        "unsupported_claim_rate": round(1.0 - citation_rate, 12),
        "suggested_check_exact_match_rate": round(useful_matched / useful_expected, 12),
        "prompt_injection_resilience_rate": round(injection_resisted / injection_expected, 12),
        "stability_rate": round(stable_cases / valid_expected, 12),
        "counts": {
            "valid_cases": valid_expected,
            "invalid_negative_controls": invalid_expected,
            "claims": claims,
            "supported_claims": supported_claims,
        },
        "usage": {
            "input_tokens_conservative_fake": input_tokens,
            "output_tokens_conservative_fake": output_tokens,
            "cost_microusd": cost_microusd,
        },
        "per_case": per_case,
    }


def _latency(fixture: dict[str, Any]) -> dict[str, object]:
    samples: list[float] = []
    for _index in range(LATENCY_REPETITIONS):
        started = time.perf_counter_ns()
        _evaluate(fixture)
        samples.append((time.perf_counter_ns() - started) / 1_000_000.0)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, int(0.95 * len(ordered)))
    return {
        "measurement": "single-process full synthetic fake-provider suite",
        "repetitions": LATENCY_REPETITIONS,
        "median_ms": round(statistics.median(samples), 6),
        "p95_ms": round(ordered[p95_index], 6),
        "minimum_ms": round(min(samples), 6),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor() or "not reported",
        },
        "limitations": (
            "This is deterministic in-process fake-provider latency. It excludes provider, "
            "database, queue, and network time."
        ),
    }


def _stable_artifact(fixture: dict[str, Any]) -> dict[str, object]:
    return {
        "schema_version": LLM_EVALUATION_VERSION,
        "synthetic": True,
        "fixture": {
            "path": FIXTURE_PATH.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(_canonical_json(fixture)).hexdigest(),
            "case_count": len(fixture["cases"]),
            "license": fixture["license"],
            "usage": fixture["usage"],
        },
        "configuration": {
            "provider": "deterministic_fake",
            "model": "deterministic-evidence-synthesizer-v1",
            "prompt_version": PROMPT_IDENTITY.prompt_version,
            "prompt_sha256": PROMPT_IDENTITY.prompt_sha256,
            "schema_version": PROMPT_IDENTITY.schema_version,
            "schema_sha256": PROMPT_IDENTITY.schema_sha256,
            "stability_repetitions": STABILITY_REPETITIONS,
        },
        "quality": _evaluate(fixture),
        "decision": {
            "hosted_provider_executed": False,
            "hosted_provider_enabled_by_default": False,
            "deterministic_fake_is_default": True,
            "reason": (
                "The frozen synthetic suite validates schema, citation, routing-adjacent, "
                "injection, missing/conflicting evidence, budget and failure contracts. It "
                "does not establish hosted-model usefulness or customer outcomes."
            ),
        },
        "limitations": [
            "All evidence, outputs, and usefulness judgments are explicitly synthetic.",
            (
                "Suggested-check usefulness is an exact deterministic gold-rubric match, "
                "not model self-grading."
            ),
            "No paid or hosted provider was called and no customer/public source was transmitted.",
            (
                "Provider quality, real latency, billed cost, retention, and regional behavior "
                "are not yet validated."
            ),
        ],
    }


def _with_hash_and_latency(
    stable: dict[str, object], latency: dict[str, object]
) -> dict[str, object]:
    artifact = {**stable, "latency_evidence": latency}
    root_hash = hashlib.sha256(_canonical_json(artifact)).hexdigest()
    return {**artifact, "root_sha256": root_hash}


def _verify() -> None:
    fixture = _load_fixture()
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    root_hash = committed.pop("root_sha256", None)
    if root_hash != hashlib.sha256(_canonical_json(committed)).hexdigest():
        raise ValueError("committed M7 evaluation artifact checksum is invalid")
    expected_stable = _stable_artifact(fixture)
    committed_stable = {key: value for key, value in committed.items() if key != "latency_evidence"}
    if committed_stable != expected_stable:
        raise ValueError("committed M7 evaluation quality/configuration is stale")
    print(json.dumps({"status": "verified", "current_latency": _latency(fixture)}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("choose exactly one of --write or --check")
    if args.write:
        fixture = _load_fixture()
        artifact = _with_hash_and_latency(_stable_artifact(fixture), _latency(fixture))
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_bytes(_canonical_json(artifact))
        print(f"wrote {ARTIFACT_PATH.relative_to(ROOT)}")
    else:
        _verify()
    return 0


if __name__ == "__main__":
    sys.exit(main())
