"""Build or verify deterministic M10 differential, mutation and policy evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from packages.execution_contracts import (
    DIFFERENTIAL_FIXTURE_BUNDLE_SHA256,
    SafeOutputV1,
    WorkloadObservationV1,
    WorkloadOutcome,
    compare_observations,
    compute_differential_bundle_sha256,
)
from packages.recommendation_core import (
    ComponentEvidence,
    ComponentStatus,
    Recommendation,
    RecommendationInputsV1,
    fuse_recommendation,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "execution" / "m10_differential_cases_v1.json"
BUNDLE_PATH = ROOT / "tests" / "fixtures" / "differential" / "releaseproof_m10"
ARTIFACT_PATH = ROOT / "artifacts" / "evaluation" / "m10_differential_eval_v1.json"


def _json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _load_fixture() -> dict[str, Any]:
    value = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if (
        value.get("schema_version") != "m10-differential-evaluation-fixture-v1"
        or value.get("synthetic") is not True
    ):
        raise ValueError("M10 evaluation fixture identity is invalid")
    return cast(dict[str, Any], value)


def _observation(outcome: str, total: str | None) -> WorkloadObservationV1:
    resolved = WorkloadOutcome(outcome)
    empty = SafeOutputV1.capture(b"", limit=4_096)
    available = total is not None
    return WorkloadObservationV1(
        outcome=resolved,
        test_exit_code=0
        if resolved is WorkloadOutcome.PASSED
        else None
        if resolved is WorkloadOutcome.TIMEOUT
        else 1,
        test_elapsed_milliseconds=10,
        probe_exit_code=0 if available else None,
        probe_elapsed_milliseconds=2,
        http=(
            {
                "body": {"currency": "CAD", "total": total},
                "headers": {"x-request-id": "masked"},
                "schema": {"currency": "string", "total": "string"},
                "status": 200,
            }
            if available
            else None
        ),
        state={"quote_count": 1, "updated_at": "masked"} if available else None,
        events=(({"name": "quote.calculated", "sequence": 1},) if available else ()),
        stdout=empty,
        stderr=empty,
    )


def _component(name: str) -> ComponentEvidence:
    return ComponentEvidence(
        status=ComponentStatus.AVAILABLE,
        fact="clear",
        evidence_ids=(f"fixture:{name}",),
    )


def _policy_inputs() -> RecommendationInputsV1:
    return RecommendationInputsV1(
        model_risk=_component("risk"),
        retrieval=_component("retrieval"),
        generated_tests=_component("tests"),
        execution=_component("execution"),
        differential=_component("differential"),
        mutation=_component("mutation"),
        mutation_score_percent=100,
    )


def _policy_case(case_id: str) -> RecommendationInputsV1:
    inputs = _policy_inputs()
    if case_id == "complete_clear":
        return inputs
    if case_id == "missing_execution":
        return replace(
            inputs,
            execution=ComponentEvidence(ComponentStatus.MISSING, "missing", ()),
        )
    if case_id == "deterministic_hold_llm_ship":
        return replace(
            inputs,
            differential=ComponentEvidence(
                ComponentStatus.AVAILABLE,
                "regression",
                ("fixture:differential",),
                deterministic_hold=True,
            ),
            llm_suggestion=Recommendation.SHIP,
        )
    if case_id == "low_mutation_score":
        return replace(inputs, mutation_score_percent=0)
    raise ValueError("unknown M10 policy case")


def _artifact(fixture: dict[str, Any]) -> dict[str, object]:
    differential_results = []
    for case in fixture["differential_cases"]:
        base = _observation(case["base_outcome"], case["base_total"])
        candidate = _observation(case["candidate_outcome"], case["candidate_total"])
        outcome, differences = compare_observations(base, candidate)
        passed = (
            outcome.value == case["expected_outcome"]
            and list(differences) == case["expected_differences"]
        )
        differential_results.append(
            {
                "actual_differences": list(differences),
                "actual_outcome": outcome.value,
                "id": case["id"],
                "passed": passed,
            }
        )
    policy_results = []
    for case in fixture["policy_cases"]:
        decision = fuse_recommendation(_policy_case(case["id"]))
        policy_results.append(
            {
                "actual": decision.recommendation.value,
                "advisory_only": decision.advisory_only,
                "auto_merge": decision.auto_merge,
                "expected": case["expected"],
                "id": case["id"],
                "passed": decision.recommendation.value == case["expected"],
            }
        )
    bundle_hash = compute_differential_bundle_sha256(BUNDLE_PATH)
    all_passed = all(item["passed"] for item in differential_results + policy_results)
    return {
        "schema_version": "m10-differential-evaluation-v1",
        "synthetic": True,
        "fixture": {
            "license": fixture["license"],
            "path": FIXTURE_PATH.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(_json(fixture)).hexdigest(),
        },
        "bundle": {
            "matches_frozen_hash": bundle_hash == DIFFERENTIAL_FIXTURE_BUNDLE_SHA256,
            "path": BUNDLE_PATH.relative_to(ROOT).as_posix(),
            "sha256": bundle_hash,
        },
        "differential_cases": differential_results,
        "mutation": {
            **fixture["mutation_expectation"],
            "limitations": [
                "Only two controlled source mutations are evaluated.",
                "A surviving mutation indicates a possible test gap, not a production defect.",
            ],
        },
        "policy_cases": policy_results,
        "decision": {
            "all_fixture_cases_passed": all_passed,
            "bundle_identity_validated": bundle_hash == DIFFERENTIAL_FIXTURE_BUNDLE_SHA256,
            "external_repository_execution_enabled": False,
            "live_sandbox_evidence_required_in_ci": True,
        },
        "limitations": [
            "All inputs and revisions are synthetic and source controlled.",
            "Latency values are descriptive and are not a performance-regression threshold.",
            "The HTTP fixture calls a handler contract in-process and opens no network socket.",
            "Live sandbox evidence is produced separately on the disposable CI host.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("choose exactly one of --write or --check")
    expected = _artifact(_load_fixture())
    if args.write:
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_bytes(_json(expected))
        print(f"wrote {ARTIFACT_PATH.relative_to(ROOT)}")
    else:
        committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
        if committed != expected:
            raise ValueError("committed M10 evaluation artifact is stale")
        print(json.dumps({"status": "verified", "all_fixture_cases_passed": True}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
