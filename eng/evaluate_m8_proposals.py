"""Build or verify the frozen synthetic M8 generated-test evaluation artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from adapters.test_generation import PythonFixtureTestAdapter
from packages.ai_core import (
    GeneratedTestProposalV1,
    ProposalGenerationMetadata,
    ProposalRisk,
    ProposalSchemaError,
    parse_test_proposal_json,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "proposals" / "m8_static_validation_v1.json"
ARTIFACT_PATH = ROOT / "artifacts" / "evaluation" / "m8_test_proposal_eval_v1.json"
STABILITY_REPETITIONS = 5
LATENCY_REPETITIONS = 100
DEFAULT_PATH = "tests/generated/test_pricing_rounding.py"
DEFAULT_CONTENT = (
    "from fixture_app.pricing import calculate_total\n\n\n"
    "def test_pricing_rounds_once() -> None:\n"
    "    assert calculate_total(100, 5) == 105\n"
)


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _load_fixture() -> dict[str, Any]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if (
        payload.get("schema_version") != "m8-static-validation-fixture-v1"
        or payload.get("synthetic") is not True
        or not isinstance(cases, list)
        or not cases
    ):
        raise ValueError("M8 proposal fixture identity is invalid")
    return cast(dict[str, Any], payload)


def _proposal(case: dict[str, Any]) -> GeneratedTestProposalV1:
    adapter = PythonFixtureTestAdapter()
    file_path = str(case.get("file_path", DEFAULT_PATH))
    proposal = adapter.build_proposal(
        target_behavior="Pricing applies the percentage adjustment exactly once.",
        rationale="Synthetic evidence identifies a controlled rounding regression risk.",
        evidence_ids=("evidence:synthetic:pricing",),
        file_path=file_path,
        test_content=str(case.get("test_content", DEFAULT_CONTENT)),
        expected_result="The focused synthetic regression test would pass if later executed.",
        risk=ProposalRisk.MEDIUM,
        generation=ProposalGenerationMetadata(
            provider_name="deterministic_fake",
            model_id="deterministic-evidence-synthesizer-v1",
            provider_adapter_version="deterministic-llm-fake-v1",
            prompt_version="change-analysis-prompt-v1",
            prompt_sha256="a" * 64,
            source_evidence_id="evidence:00000000-0000-0000-0000-000000000001",
        ),
    )
    if "commands" in case:
        proposal = replace(
            proposal,
            commands=tuple(str(value) for value in case["commands"]),
        )
    if case.get("patch_mode") == "modify_source":
        proposal = replace(
            proposal,
            patch=(
                "--- a/fixture_app/pricing.py\n"
                "+++ b/fixture_app/pricing.py\n"
                "@@ -1,1 +1,1 @@\n"
                "-return value\n"
                "+return round(value)\n"
            ),
        )
    return proposal


def _case_result(case: dict[str, Any]) -> dict[str, object]:
    proposal = _proposal(case)
    if case.get("schema_extra") is True:
        payload = proposal.as_dict()
        payload["untrusted_extra"] = "must be rejected"
        try:
            parse_test_proposal_json(json.dumps(payload, sort_keys=True))
        except ProposalSchemaError:
            return {
                "case_id": case["case_id"],
                "expected_valid": False,
                "actual_valid": False,
                "matched_expected_code": True,
                "observed_codes": ["schema_rejected"],
                "proposal_sha256": proposal.proposal_sha256,
            }
        return {
            "case_id": case["case_id"],
            "expected_valid": False,
            "actual_valid": True,
            "matched_expected_code": False,
            "observed_codes": [],
            "proposal_sha256": proposal.proposal_sha256,
        }
    report = PythonFixtureTestAdapter().validate(proposal)
    observed_codes = [check.code for check in report.checks]
    return {
        "case_id": case["case_id"],
        "expected_valid": bool(case["expect_valid"]),
        "actual_valid": report.valid,
        "matched_expected_code": str(case["expected_code"]) in observed_codes,
        "observed_codes": observed_codes,
        "proposal_sha256": proposal.proposal_sha256,
        "content_sha256": report.content_sha256,
    }


def _evaluate(fixture: dict[str, Any]) -> dict[str, object]:
    results = [_case_result(cast(dict[str, Any], raw)) for raw in fixture["cases"]]
    valid = [result for result in results if result["expected_valid"] is True]
    invalid = [result for result in results if result["expected_valid"] is False]
    valid_accepted = sum(result["actual_valid"] is True for result in valid)
    invalid_rejected = sum(result["actual_valid"] is False for result in invalid)
    code_matches = sum(result["matched_expected_code"] is True for result in results)
    stability_hashes = {
        hashlib.sha256(
            _canonical_json([_case_result(cast(dict[str, Any], raw)) for raw in fixture["cases"]])
        ).hexdigest()
        for _index in range(STABILITY_REPETITIONS)
    }
    return {
        "valid_acceptance_rate": round(valid_accepted / len(valid), 12),
        "invalid_rejection_rate": round(invalid_rejected / len(invalid), 12),
        "false_acceptance_rate": round((len(invalid) - invalid_rejected) / len(invalid), 12),
        "expected_check_match_rate": round(code_matches / len(results), 12),
        "stability_rate": 1.0 if len(stability_hashes) == 1 else 0.0,
        "counts": {
            "cases": len(results),
            "valid_controls": len(valid),
            "invalid_adversarial_controls": len(invalid),
        },
        "per_case": results,
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
        "measurement": "single-process static parse/format/type-shape/safety suite",
        "repetitions": LATENCY_REPETITIONS,
        "median_ms": round(statistics.median(samples), 6),
        "p95_ms": round(ordered[p95_index], 6),
        "minimum_ms": round(min(samples), 6),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor() or "not reported",
        },
        "limitations": "This measures static validation only; no proposed test was executed.",
    }


def _stable_artifact(fixture: dict[str, Any]) -> dict[str, object]:
    return {
        "schema_version": "m8-test-proposal-evaluation-v1",
        "synthetic": True,
        "fixture": {
            "path": FIXTURE_PATH.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(_canonical_json(fixture)).hexdigest(),
            "case_count": len(fixture["cases"]),
            "license": fixture["license"],
            "usage": fixture["usage"],
        },
        "configuration": {
            "adapter": PythonFixtureTestAdapter.adapter_name,
            "adapter_version": PythonFixtureTestAdapter.adapter_version,
            "validator_version": PythonFixtureTestAdapter.validator_version,
            "stability_repetitions": STABILITY_REPETITIONS,
            "execution_enabled": False,
        },
        "quality": _evaluate(fixture),
        "decision": {
            "proposal_export_validated": True,
            "proposal_execution_validated": False,
            "execution_approval_created": False,
            "reason": (
                "M8 validates immutable human-reviewed proposal/export boundaries. "
                "Sandbox plans, execution approval, and execution remain M9 work."
            ),
        },
        "limitations": [
            "Every case and expected judgment is explicitly synthetic.",
            "AST safety filtering is defense in depth and is not a sandbox boundary.",
            "No generated test, patch, command, repository write, or provider call occurred.",
            "Real-repository usefulness and human acceptance quality are not yet measured.",
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
        raise ValueError("committed M8 evaluation artifact checksum is invalid")
    expected_stable = _stable_artifact(fixture)
    committed_stable = {key: value for key, value in committed.items() if key != "latency_evidence"}
    if committed_stable != expected_stable:
        raise ValueError("committed M8 evaluation quality/configuration is stale")
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
