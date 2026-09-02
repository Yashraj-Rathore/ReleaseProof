"""In-container M10 fixture differential runner; standard library only."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_BUNDLE = Path("/opt/differential")
_OVERLAYS = {
    "identical": None,
    "probe_timeout": "probe_timeout",
    "tax_regression": "tax_regression",
}
_MUTATIONS = {
    "negative_guard_removed": "negative_guard_removed",
    "tax_rate_forced": "tax_regression",
}


def _content_from_patch(file_path: str, patch: str) -> str:
    lines = patch.splitlines()
    if len(lines) < 3 or lines[0] != "--- /dev/null" or lines[1] != f"+++ b/{file_path}":
        raise ValueError("patch header invalid")
    content: list[str] = []
    seen_hunk = False
    for line in lines[2:]:
        if not seen_hunk:
            if not line.startswith("@@ -0,0 +1,"):
                raise ValueError("patch hunk invalid")
            seen_hunk = True
        elif line.startswith("+") and not line.startswith("+++"):
            content.append(line[1:])
        else:
            raise ValueError("patch is not add-only")
    if not seen_hunk:
        raise ValueError("patch hunk missing")
    return "\n".join(content) + "\n"


def _capture(raw: bytes, limit: int) -> dict[str, object]:
    return {
        "excerpt": raw[:limit].decode("utf-8", errors="replace"),
        "original_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "truncated": len(raw) > limit,
    }


def _workspace(name: str, overlay: str | None, execution_input: dict[str, str]) -> Path:
    root = Path("/workspace") / name
    shutil.copytree(_BUNDLE / "base", root)
    if overlay is not None:
        shutil.copytree(_BUNDLE / "overlays" / overlay, root, dirs_exist_ok=True)
    target = root / execution_input["file_path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        _content_from_patch(execution_input["file_path"], execution_input["patch"]),
        encoding="utf-8",
    )
    return root


def _run_process(
    command: list[str], *, root: Path, environment: dict[str, str], timeout: int
) -> tuple[int | None, int, bytes, bytes, bool]:
    started = time.monotonic()
    process = subprocess.Popen(  # noqa: S603
        command,
        cwd=root,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode, int((time.monotonic() - started) * 1000), stdout, stderr, False
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        return None, int((time.monotonic() - started) * 1000), stdout, stderr, True


def _observation(
    *, root: Path, execution_input: dict[str, str], plan: dict[str, Any]
) -> dict[str, object]:
    environment = dict(plan["environment"])
    environment["PYTHONPATH"] = str(root / "src")
    timeout = int(plan["resources"]["wall_time_seconds"])
    test = _run_process(
        [sys.executable, "-m", "pytest", "-q", execution_input["file_path"]],
        root=root,
        environment=environment,
        timeout=timeout,
    )
    probe = _run_process(
        [sys.executable, "-m", "fixture_app.contract_probe"],
        root=root,
        environment=environment,
        timeout=timeout,
    )
    http: dict[str, object] | None = None
    state: dict[str, object] | None = None
    events: list[dict[str, object]] = []
    probe_invalid = False
    if probe[0] == 0 and not probe[4]:
        try:
            payload = json.loads(probe[2])
            if not isinstance(payload, dict):
                raise ValueError
            http = payload["http"]
            state = payload["state"]
            events = payload["events"]
            if (
                not isinstance(http, dict)
                or not isinstance(state, dict)
                or not isinstance(events, list)
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            probe_invalid = True
    if test[4] or probe[4]:
        outcome = "timeout"
    elif probe_invalid:
        outcome = "unavailable"
    elif test[0] == 0 and probe[0] == 0:
        outcome = "passed"
    else:
        outcome = "failed"
    output_limit = int(plan["resources"]["output_bytes"])
    return {
        "events": events,
        "http": http,
        "outcome": outcome,
        "probe_elapsed_milliseconds": probe[1],
        "probe_exit_code": probe[0],
        "state": state,
        "stderr": _capture(test[3] + probe[3], output_limit),
        "stdout": _capture(test[2] + probe[2], output_limit),
        "test_elapsed_milliseconds": test[1],
        "test_exit_code": test[0],
    }


def _mutation(
    *, mutation_id: str, root: Path, execution_input: dict[str, str], plan: dict[str, Any]
) -> dict[str, object]:
    environment = dict(plan["environment"])
    environment["PYTHONPATH"] = str(root / "src")
    completed = _run_process(
        [sys.executable, "-m", "pytest", "-q", execution_input["file_path"]],
        root=root,
        environment=environment,
        timeout=int(plan["resources"]["wall_time_seconds"]),
    )
    if completed[4] or completed[0] is None:
        outcome = "inconclusive"
    else:
        outcome = "survived" if completed[0] == 0 else "killed"
    return {
        "elapsed_milliseconds": completed[1],
        "exit_code": completed[0],
        "mutation_id": mutation_id,
        "outcome": outcome,
    }


def _selected_state(value: object) -> object:
    if not isinstance(value, dict):
        return value
    return {key: item for key, item in value.items() if key != "updated_at"}


def _compare(base: dict[str, object], candidate: dict[str, object]) -> tuple[str, list[str]]:
    if base["outcome"] != "passed":
        return "base_failed", []
    if candidate["outcome"] in {"timeout", "unavailable"}:
        return "unknown", []
    differences: list[str] = []
    if candidate["outcome"] != "passed":
        differences.append("tests.outcome")
    base_http = base["http"]
    candidate_http = candidate["http"]
    if isinstance(base_http, dict) and isinstance(candidate_http, dict):
        for key, code in (
            ("status", "http.status"),
            ("schema", "http.schema"),
            ("body", "http.body"),
        ):
            if base_http.get(key) != candidate_http.get(key):
                differences.append(code)
    elif base_http != candidate_http:
        differences.append("http.missing")
    if _selected_state(base["state"]) != _selected_state(candidate["state"]):
        differences.append("state.selected")
    if base["events"] != candidate["events"]:
        differences.append("events.selected")
    return ("difference", differences) if differences else ("no_difference", [])


def run(payload: dict[str, Any], checks: dict[str, bool]) -> int:
    plan = payload["differential_plan"]
    execution_input = payload["input"]
    variant = plan["candidate_variant"]
    if variant not in _OVERLAYS or any(item not in _MUTATIONS for item in plan["mutation_ids"]):
        return 64
    base_root = _workspace("base", None, execution_input)
    candidate_root = _workspace("candidate", _OVERLAYS[variant], execution_input)
    base = _observation(root=base_root, execution_input=execution_input, plan=plan)
    candidate = _observation(root=candidate_root, execution_input=execution_input, plan=plan)
    mutations = []
    for mutation_id in plan["mutation_ids"]:
        root = _workspace(f"mutation-{mutation_id}", _MUTATIONS[mutation_id], execution_input)
        mutations.append(
            _mutation(
                mutation_id=mutation_id,
                root=root,
                execution_input=execution_input,
                plan=plan,
            )
        )
    outcome, differences = _compare(base, candidate)
    killed = sum(item["outcome"] == "killed" for item in mutations)
    total = sum(item["outcome"] != "inconclusive" for item in mutations)
    result = {
        "attempt": payload["attempt"],
        "base": base,
        "candidate": candidate,
        "cleanup_succeeded": False,
        "differences": differences,
        "image": plan["image"],
        "isolation_checks": checks,
        "limitations": [
            "synthetic_fixture_only",
            "bounded_mutation_operators_not_exhaustive",
            "latency_is_descriptive_not_a_performance_regression_gate",
        ],
        "mask_policy_version": "releaseproof.fixture-mask.v1",
        "mutation_killed": killed,
        "mutation_set_version": "releaseproof.fixture-mutations.v1",
        "mutation_total": total,
        "mutations": mutations,
        "outcome": outcome,
        "plan_sha256": plan["plan_sha256"],
        "runner_version": "releaseproof-differential-runner-v1",
        "schema_version": "releaseproof.differential-result.v1",
        "workload_version": "releaseproof.fixture-workload.v1",
    }
    canonical = json.dumps(
        result, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    result["result_sha256"] = hashlib.sha256(canonical.encode("ascii")).hexdigest()
    sys.stdout.write(
        json.dumps(
            result, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        )
    )
    return 0
