"""Measure and verify bounded synthetic M14 security/reliability/operations evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from adapters.tasks.fake import FakeTaskPublisher
from eng import (
    evaluate_m4_baseline as m4,
)
from eng import (
    evaluate_m6_retrieval as m6,
)
from eng import (
    evaluate_m7_llm as m7,
)
from eng import (
    evaluate_m8_proposals as m8,
)
from eng import (
    evaluate_m9_runner as m9,
)
from eng import (
    evaluate_m10_differential as m10,
)
from eng import (
    evaluate_m12_agent as m12,
)
from packages.domain import TaskMessage
from packages.ml_core import evaluate_baseline
from packages.observability import expected_failure_drills

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "artifacts" / "evaluation" / "m14_operations_eval_v1.json"
PIPELINE_REPETITIONS = 20
QUEUE_MESSAGES = 1_000


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def _json(path: Path) -> dict[str, Any]:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return cast(dict[str, Any], value)


def _percentiles(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "median_ms": round(statistics.median(ordered), 6),
        "minimum_ms": round(ordered[0], 6),
        "p95_ms": round(ordered[p95_index], 6),
    }


def _exercise_control_plane() -> str:
    """Sequence the established fixture stages without network, DB, or code execution."""

    dataset = m4.build_fixture_dataset(extraction_code_commit="0" * 40)
    baseline = evaluate_baseline(dataset)
    retrieval = m6._quality(m6._load_fixture())
    llm = m7._evaluate(m7._load_fixture())
    proposals = m8._evaluate(m8._load_fixture())
    runner_contract = m9._artifact(m9._load_fixture())
    differential = m10._artifact(m10._load_fixture())
    agent = m12._evaluate(m12._load_fixture())
    retrieval_hybrid = cast(dict[str, object], retrieval["hybrid_rrf"])
    runner_quality = cast(dict[str, object], runner_contract["quality"])
    evidence = {
        "agent": agent["controls"],
        "baseline": baseline["baseline_artifact_hash"],
        "differential": differential["decision"],
        "llm": llm["schema_validity_rate"],
        "proposal": proposals["invalid_rejection_rate"],
        "retrieval": retrieval_hybrid["recall_at_k"],
        "runner": runner_quality["all_checks_passed"],
    }
    return hashlib.sha256(_canonical_bytes(evidence)).hexdigest()


def _pipeline_latency() -> dict[str, object]:
    samples: list[float] = []
    digests: set[str] = set()
    for _index in range(PIPELINE_REPETITIONS):
        started = time.perf_counter_ns()
        digests.add(_exercise_control_plane())
        samples.append((time.perf_counter_ns() - started) / 1_000_000.0)
    if len(digests) != 1:
        raise ValueError("representative fixture pipeline was not deterministic")
    return {
        **_percentiles(samples),
        "measurement": (
            "single-process sequential synthetic PR control-plane fixture: deterministic "
            "baseline, retrieval, fake LLM, static proposal validation, runner contract, "
            "differential policy and bounded agent"
        ),
        "repetitions": PIPELINE_REPETITIONS,
        "stable_result_sha256": next(iter(digests)),
    }


def _queue_measurement() -> dict[str, object]:
    publisher = FakeTaskPublisher()
    started = time.perf_counter_ns()
    for index in range(QUEUE_MESSAGES):
        publisher.publish(
            TaskMessage(
                topic="releaseproof.analysis.process_job.v1",
                payload={
                    "organization_id": "00000000-0000-0000-0000-000000000001",
                    "job_id": f"00000000-0000-0000-0000-{index:012d}",
                },
                idempotency_key=f"m14-queue-{index}",
            )
        )
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
    return {
        "messages": len(publisher.messages),
        "elapsed_ms": round(elapsed_ms, 6),
        "peak_in_memory_depth": len(publisher.messages),
        "measurement": "deterministic in-process publisher burst",
        "redis_or_celery_latency_measured": False,
    }


def _prior_stage_evidence() -> dict[str, object]:
    paths = {
        "retrieval": ROOT / "artifacts/evaluation/m6_retrieval_eval_v1.json",
        "llm": ROOT / "artifacts/evaluation/m7_llm_eval_v1.json",
        "proposal": ROOT / "artifacts/evaluation/m8_test_proposal_eval_v1.json",
        "runner": ROOT / "artifacts/evaluation/m9_runner_eval_v1.json",
        "differential": ROOT / "artifacts/evaluation/m10_differential_eval_v1.json",
        "semantic": ROOT / "artifacts/evaluation/m11_semantic_eval_v1.json",
        "agent": ROOT / "artifacts/evaluation/m12_agent_eval_v1.json",
        "governance": ROOT / "artifacts/evaluation/m13_governance_eval_v1.json",
    }
    return {
        name: {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "latency_evidence": _json(path).get("latency_evidence"),
        }
        for name, path in paths.items()
    }


def build_artifact() -> dict[str, object]:
    drills = expected_failure_drills()
    return {
        "schema_version": "m14-operations-evaluation-v1",
        "synthetic": True,
        "measured_at": datetime.now(tz=UTC).isoformat(),
        "environment": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        },
        "security_review": {
            "report": "docs/51_M14_SECURITY_RELIABILITY_REVIEW.md",
            "critical_open": 0,
            "high_open": 0,
            "external_repository_execution_enabled": False,
        },
        "failure_drills": [
            {
                "component": drill.component.value,
                "injected_failure": drill.injected_failure,
                "expected_disposition": drill.expected_disposition.value,
                "false_ship_possible": drill.false_ship_possible,
            }
            for drill in drills
        ],
        "performance": {
            "representative_control_plane": _pipeline_latency(),
            "queue": _queue_measurement(),
            "prior_stage_evidence": _prior_stage_evidence(),
            "percentile_method": "nearest-rank p95 over wall-clock perf_counter_ns samples",
        },
        "cost": {
            "deterministic_fixture_external_cost_usd": 0.0,
            "hosted_llm_billed_cost": None,
            "external_runner_billed_cost": None,
            "production_infrastructure_cost": None,
            "status": "not_yet_measured_outside_local_fixture",
        },
        "claims": {
            "capacity_validated": False,
            "customer_latency_validated": False,
            "hosted_provider_latency_validated": False,
            "production_runner_latency_validated": False,
        },
        "limitations": [
            "The end-to-end figure is a sequential in-process synthetic control-plane work "
            "sample; it excludes PostgreSQL, Redis/Celery, network, hosted providers and a "
            "live sandbox.",
            "The queue figure measures the deterministic publisher contract, not Redis or "
            "Celery throughput, scheduling delay or worker saturation.",
            "Prior component latencies were measured on their recorded local environments and "
            "must not be added together as a production latency estimate.",
            "No customer workload, paid LLM call, external repository execution, load test or "
            "capacity extrapolation was performed.",
            "All monetary values other than the zero-cost local fake remain not yet measured.",
        ],
    }


def _with_hash(value: dict[str, object]) -> dict[str, object]:
    return value | {"root_sha256": hashlib.sha256(_canonical_bytes(value)).hexdigest()}


def _verify() -> None:
    committed = _json(ARTIFACT_PATH)
    root_sha256 = committed.pop("root_sha256", None)
    if root_sha256 != hashlib.sha256(_canonical_bytes(committed)).hexdigest():
        raise ValueError("committed M14 operations evidence checksum is invalid")
    drills = committed.get("failure_drills")
    if not isinstance(drills, list) or len(drills) != 7:
        raise ValueError("M14 failure-drill coverage is incomplete")
    if any(
        not isinstance(item, dict) or item.get("false_ship_possible") is not False
        for item in drills
    ):
        raise ValueError("M14 failure drill permits a false SHIP")
    review = committed.get("security_review")
    claims = committed.get("claims")
    if (
        not isinstance(review, dict)
        or review.get("critical_open") != 0
        or review.get("high_open") != 0
    ):
        raise ValueError("M14 security review has an unresolved Critical/High finding")
    if not isinstance(claims, dict) or any(value is not False for value in claims.values()):
        raise ValueError("M14 evidence makes an unsupported validation claim")
    print(json.dumps({"root_sha256": root_sha256, "status": "verified"}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("choose exactly one of --write or --check")
    if args.write:
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_bytes(_canonical_bytes(_with_hash(build_artifact())))
        print(f"wrote {ARTIFACT_PATH.relative_to(ROOT)}")
    else:
        _verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
