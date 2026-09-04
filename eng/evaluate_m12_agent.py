"""Build or verify the frozen synthetic M12 agent/non-agent comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import time
from pathlib import Path
from typing import Any, cast

from adapters.agent import DeterministicAgentNodeProvider
from adapters.llm import FakeLLMProvider
from packages.agent_core import (
    AGENT_EVALUATION_VERSION,
    AgentLimits,
    BoundedInvestigationTools,
    CriticVerdict,
    EvidenceCategory,
    EvidenceReference,
    InvestigationRequest,
    ToolName,
    run_investigation,
)
from packages.ai_core import ContentClass, EvidenceContext, LLMBudget, build_analysis_request
from packages.ai_core.evaluation import evaluate_suggestion
from packages.recommendation_core import (
    ComponentEvidence,
    ComponentStatus,
    Recommendation,
    RecommendationInputsV1,
    fuse_recommendation,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "agents" / "m12_investigation_v1.json"
ARTIFACT_PATH = ROOT / "artifacts" / "evaluation" / "m12_agent_eval_v1.json"
LATENCY_REPETITIONS = 25


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def _load_fixture() -> dict[str, Any]:
    value = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = value.get("cases")
    if (
        value.get("schema_version") != "m12-agent-fixture-v1"
        or value.get("synthetic") is not True
        or not isinstance(cases, list)
        or len(cases) < 4
    ):
        raise ValueError("M12 fixture identity is invalid")
    return cast(dict[str, Any], value)


def _component(
    case_id: str,
    name: str,
    *,
    status: ComponentStatus = ComponentStatus.AVAILABLE,
    fact: str = "clear",
    hold: bool = False,
) -> ComponentEvidence:
    return ComponentEvidence(
        status=status,
        fact=fact,
        evidence_ids=()
        if status is not ComponentStatus.AVAILABLE
        else (f"policy:{case_id}:{name}",),
        deterministic_hold=hold,
    )


def _policy_inputs(case: dict[str, Any]) -> RecommendationInputsV1:
    case_id = str(case["case_id"])
    policy_case = str(case["policy_case"])
    values = {
        name: _component(case_id, name)
        for name in (
            "model_risk",
            "retrieval",
            "generated_tests",
            "execution",
            "differential",
            "mutation",
        )
    }
    if policy_case == "hold":
        values["execution"] = _component(case_id, "execution", fact="failed", hold=True)
    elif policy_case == "unknown":
        values["retrieval"] = _component(
            case_id,
            "retrieval",
            status=ComponentStatus.MISSING,
            fact="missing",
        )
    elif policy_case == "review":
        values["mutation"] = _component(case_id, "mutation", fact="survived")
    elif policy_case != "ship":
        raise ValueError("unknown fixture policy case")
    return RecommendationInputsV1(
        model_risk=values["model_risk"],
        retrieval=values["retrieval"],
        generated_tests=values["generated_tests"],
        execution=values["execution"],
        differential=values["differential"],
        mutation=values["mutation"],
        mutation_score_percent=100,
    )


def _evidence(case: dict[str, Any]) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            evidence_id=f"evidence:{case['case_id']}:{item['category']}",
            category=EvidenceCategory(str(item["category"])),
            summary=f"Synthetic {item['category']} summary for {case['case_id']}.",
            source_reference=f"fixture:{case['case_id']}:{item['category']}",
            fact_codes=(str(item["fact_code"]),),
        )
        for item in case["evidence"]
    )


def _limits(case: dict[str, Any]) -> AgentLimits:
    values = AgentLimits().as_dict()
    overrides = case["limit_overrides"]
    if not isinstance(overrides, dict):
        raise ValueError("limit overrides must be an object")
    values.update(overrides)
    return AgentLimits(**values)  # type: ignore[arg-type]


def _agent_case(case: dict[str, Any]) -> dict[str, object]:
    evidence = _evidence(case)
    limits = _limits(case)
    decision = fuse_recommendation(_policy_inputs(case))
    request = InvestigationRequest(
        run_id=f"agent:evaluation:{case['case_id']}",
        snapshot_id=f"snapshot:{case['case_id']}",
        evidence=evidence,
        policy_decision=decision,
        limits=limits,
        cancelled=bool(case["cancelled"]),
    )
    provider = DeterministicAgentNodeProvider()
    result = run_investigation(
        request,
        tools=BoundedInvestigationTools(
            evidence,
            limits,
            failed_tools=tuple(ToolName(item) for item in case["failed_tools"]),
        ),
        provider=provider,
    )
    expected_recommendation = Recommendation(str(case["expected_recommendation"]))
    expected_termination = str(case["expected_termination"])
    critic_passed = result.critic is None or result.critic.verdict is CriticVerdict.ACCEPT
    return {
        "case_id": case["case_id"],
        "comparison": bool(case["comparison"]),
        "critic_passed": critic_passed,
        "grounded_claims": result.critic.supported_claim_count if result.critic else 0,
        "claims": result.critic.claim_count if result.critic else 0,
        "recommendation": result.recommendation.value,
        "termination": result.termination_reason.value,
        "task_success": (
            result.recommendation is expected_recommendation
            and result.termination_reason.value == expected_termination
            and critic_passed
        ),
        "usage": result.usage.as_dict(),
    }


def _baseline_budget() -> LLMBudget:
    return LLMBudget(
        max_input_bytes=65_536,
        max_input_tokens=65_536,
        max_output_tokens=2_048,
        max_cost_microusd=100_000,
        connect_timeout_seconds=5.0,
        read_timeout_seconds=30.0,
        max_attempts=1,
        retry_backoff_seconds=0.0,
    )


def _baseline_case(case: dict[str, Any]) -> dict[str, object]:
    evidence = _evidence(case)
    request = build_analysis_request(
        change_id=f"evaluation:{case['case_id']}",
        evidence=tuple(
            EvidenceContext(
                evidence_id=item.evidence_id,
                content_class=ContentClass.DETERMINISTIC_EVIDENCE,
                content=json.dumps(item.safe_dict(), sort_keys=True),
                source_reference=item.source_reference,
            )
            for item in evidence
        ),
        budget=_baseline_budget(),
    )
    response = FakeLLMProvider().analyze_change(request)
    grounding = evaluate_suggestion(
        response.suggestion,
        allowed_evidence_ids=request.allowed_evidence_ids,
    )
    decision = fuse_recommendation(_policy_inputs(case))
    return {
        "case_id": case["case_id"],
        "grounded_claims": grounding.supported_claim_count,
        "claims": grounding.claim_count,
        "recommendation": decision.recommendation.value,
        "task_success": decision.recommendation.value == case["expected_recommendation"],
        "usage": {
            "cost_microusd": response.usage.cost_microusd,
            "input_tokens": response.usage.input_tokens,
            "llm_calls": 1,
            "output_tokens": response.usage.output_tokens,
            "steps": 1,
            "tool_calls": 0,
            "tool_errors": 0,
        },
    }


def _aggregate(rows: list[dict[str, object]]) -> dict[str, object]:
    usage_rows = [cast(dict[str, int], row["usage"]) for row in rows]
    claims = sum(cast(int, row["claims"]) for row in rows)
    grounded = sum(cast(int, row["grounded_claims"]) for row in rows)
    tool_calls = sum(item["tool_calls"] for item in usage_rows)
    tool_errors = sum(item["tool_errors"] for item in usage_rows)
    return {
        "task_success_rate": round(sum(bool(row["task_success"]) for row in rows) / len(rows), 12),
        "groundedness_rate": round(1.0 if claims == 0 else grounded / claims, 12),
        "tool_error_rate": round(0.0 if tool_calls == 0 else tool_errors / tool_calls, 12),
        "counts": {
            "cases": len(rows),
            "claims": claims,
            "grounded_claims": grounded,
            "tool_calls": tool_calls,
            "tool_errors": tool_errors,
        },
        "usage_totals": {
            name: sum(item[name] for item in usage_rows)
            for name in (
                "steps",
                "tool_calls",
                "tool_errors",
                "llm_calls",
                "input_tokens",
                "output_tokens",
                "cost_microusd",
            )
        },
    }


def _evaluate(fixture: dict[str, Any]) -> dict[str, object]:
    cases = [cast(dict[str, Any], value) for value in fixture["cases"]]
    agent_rows = [_agent_case(case) for case in cases]
    comparison_cases = [case for case in cases if bool(case["comparison"])]
    comparison_ids = {str(case["case_id"]) for case in comparison_cases}
    comparison_agent = [row for row in agent_rows if str(row["case_id"]) in comparison_ids]
    baseline_rows = [_baseline_case(case) for case in comparison_cases]
    return {
        "comparison": {
            "agent": _aggregate(comparison_agent),
            "non_agent_m7": _aggregate(baseline_rows),
        },
        "controls": {
            "all_expected_outcomes_matched": all(bool(row["task_success"]) for row in agent_rows),
            "budget_stop_count": sum(
                row["termination"] == "step_budget_exceeded" for row in agent_rows
            ),
            "cancelled_stop_count": sum(row["termination"] == "cancelled" for row in agent_rows),
            "tool_failure_stop_count": sum(
                row["termination"] == "tool_failure" for row in agent_rows
            ),
        },
        "per_case": agent_rows,
    }


def _timed(fixture: dict[str, Any], *, agent: bool) -> float:
    cases = [cast(dict[str, Any], item) for item in fixture["cases"] if item["comparison"]]
    started = time.perf_counter_ns()
    if agent:
        for case in cases:
            _agent_case(case)
    else:
        for case in cases:
            _baseline_case(case)
    return (time.perf_counter_ns() - started) / 1_000_000.0


def _latency(fixture: dict[str, Any]) -> dict[str, object]:
    agent_samples = [_timed(fixture, agent=True) for _index in range(LATENCY_REPETITIONS)]
    baseline_samples = [_timed(fixture, agent=False) for _index in range(LATENCY_REPETITIONS)]

    def summary(samples: list[float]) -> dict[str, float]:
        ordered = sorted(samples)
        p95_index = min(len(ordered) - 1, int(0.95 * len(ordered)))
        return {
            "median_ms": round(statistics.median(samples), 6),
            "minimum_ms": round(min(samples), 6),
            "p95_ms": round(ordered[p95_index], 6),
        }

    return {
        "agent": summary(agent_samples),
        "non_agent_m7": summary(baseline_samples),
        "repetitions": LATENCY_REPETITIONS,
        "measurement": "single-process four-case synthetic local-only comparison",
        "environment": {
            "platform": platform.platform(),
            "processor": platform.processor() or "not reported",
            "python": platform.python_version(),
        },
        "limitations": (
            "In-process deterministic fake latency excludes provider, database, queue, network, "
            "and sandbox time."
        ),
    }


def _stable_artifact(fixture: dict[str, Any]) -> dict[str, object]:
    quality = _evaluate(fixture)
    comparison = cast(dict[str, dict[str, object]], quality["comparison"])
    agent = comparison["agent"]
    baseline = comparison["non_agent_m7"]
    promoted = (
        cast(float, agent["task_success_rate"]) > cast(float, baseline["task_success_rate"])
        or cast(float, agent["groundedness_rate"]) > cast(float, baseline["groundedness_rate"])
    ) and cast(float, agent["tool_error_rate"]) <= cast(float, baseline["tool_error_rate"])
    return {
        "schema_version": AGENT_EVALUATION_VERSION,
        "synthetic": True,
        "fixture": {
            "case_count": len(fixture["cases"]),
            "license": fixture["license"],
            "path": FIXTURE_PATH.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(_canonical_json(fixture)).hexdigest(),
            "usage": fixture["usage"],
        },
        "configuration": {
            "agent_graph": "bounded-investigation-graph-v1",
            "agent_provider": "deterministic-agent-node-v1",
            "critic": "deterministic-structured-evidence-critic-v1",
            "non_agent_provider": "deterministic-evidence-synthesizer-v1",
            "recommendation_policy": "recommendation-fusion-v1",
        },
        "quality": quality,
        "decision": {
            "agent_enabled_by_default": False,
            "agent_promoted": promoted,
            "deterministic_fake_only": True,
            "hosted_provider_executed": False,
            "reason": (
                "The synthetic comparison shows no task-success or groundedness improvement over "
                "the simpler M7 path, while the graph uses more orchestration calls/steps and has "
                "higher measured local latency. Keep it optional."
            ),
        },
        "limitations": [
            "All cases, facts, expected outcomes, and summaries are synthetic CC0 controls.",
            "No paid/hosted provider, customer code, public repository, or sandbox execution ran.",
            "Structured fact-code entailment does not establish free-text semantic entailment.",
            "The tiny deterministic suite validates controls, not customer usefulness or safety.",
        ],
    }


def _with_latency_and_hash(
    stable: dict[str, object], latency: dict[str, object]
) -> dict[str, object]:
    artifact = {**stable, "latency_evidence": latency}
    return {**artifact, "root_sha256": hashlib.sha256(_canonical_json(artifact)).hexdigest()}


def _verify() -> None:
    fixture = _load_fixture()
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    root_hash = committed.pop("root_sha256", None)
    if root_hash != hashlib.sha256(_canonical_json(committed)).hexdigest():
        raise ValueError("committed M12 evaluation artifact checksum is invalid")
    committed_stable = {key: value for key, value in committed.items() if key != "latency_evidence"}
    if committed_stable != _stable_artifact(fixture):
        raise ValueError("committed M12 agent evaluation is stale")
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
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_bytes(
            _canonical_json(_with_latency_and_hash(_stable_artifact(fixture), _latency(fixture)))
        )
        print(f"wrote {ARTIFACT_PATH.relative_to(ROOT)}")
    else:
        _verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
