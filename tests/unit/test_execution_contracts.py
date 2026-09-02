from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from packages.execution_contracts import (
    ExecutionContractError,
    ExecutionOutcome,
    ExecutionPlanV1,
    ExecutionResultV1,
    FixtureExecutionInputV1,
    HostProfile,
    SafeOutputV1,
    compute_tree_sha256,
    parse_execution_plan_json,
    parse_execution_result_json,
    sign_payload,
    verify_payload_signature,
)
from runner.docker_cli import (
    RunnerRejectedError,
    _classify_runner_failure,
    _safe_ephemeral_ci_diagnostic,
    docker_create_arguments,
)

FIXTURE_ROOT = Path("tests/fixtures/repositories/releaseproof_fixture")


def _input() -> FixtureExecutionInputV1:
    return FixtureExecutionInputV1(
        proposal_hash="a" * 64,
        file_path="tests/generated/test_pricing.py",
        patch=(
            "--- /dev/null\n+++ b/tests/generated/test_pricing.py\n"
            "@@ -0,0 +1,2 @@\n+def test_value() -> None:\n+    assert True\n"
        ),
    )


def _plan() -> ExecutionPlanV1:
    execution_input = _input()
    return ExecutionPlanV1(
        organization_id="00000000-0000-0000-0000-000000000001",
        repository_id="00000000-0000-0000-0000-000000000002",
        snapshot_id="00000000-0000-0000-0000-000000000003",
        checkout_sha="b" * 40,
        proposal_id="00000000-0000-0000-0000-000000000004",
        proposal_hash=execution_input.proposal_hash,
        proposal_input_sha256=execution_input.input_sha256,
        fixture_tree_sha256=compute_tree_sha256(FIXTURE_ROOT),
        image=f"releaseproof/fixture-runner@sha256:{'c' * 64}",
        commands=(("python", "-m", "pytest", "-q", execution_input.file_path),),
        host_profile=HostProfile.EPHEMERAL_CI_FIXTURE,
    )


def _result(plan: ExecutionPlanV1) -> ExecutionResultV1:
    empty = SafeOutputV1.capture(b"", limit=plan.resources.output_bytes)
    return ExecutionResultV1(
        plan_sha256=plan.plan_sha256,
        image=plan.image,
        attempt=1,
        outcome=ExecutionOutcome.PASSED,
        elapsed_milliseconds=12,
        exit_code=0,
        stdout=empty,
        stderr=empty,
        timed_out=False,
        killed=False,
        cleanup_succeeded=True,
        isolation_checks=(("fixture_boundary", True),),
    )


def test_plan_and_result_round_trip_with_stable_hashes_and_signatures() -> None:
    plan = _plan()
    result = _result(plan)
    key = b"m9-test-signing-key-is-at-least-32-bytes"

    assert parse_execution_plan_json(plan.canonical_bytes().decode()) == plan
    assert parse_execution_result_json(result.canonical_bytes().decode()) == result
    signature = sign_payload(plan.canonical_bytes(), key=key)
    assert verify_payload_signature(plan.canonical_bytes(), signature=signature, key=key)
    assert not verify_payload_signature(plan.canonical_bytes() + b" ", signature=signature, key=key)
    assert plan.plan_sha256 != replace(plan, checkout_sha="d" * 40).plan_sha256


def test_plan_parser_rejects_duplicate_fields_extra_fields_and_hash_tampering() -> None:
    plan = _plan()
    raw = plan.canonical_bytes().decode()
    duplicate = raw[:-1] + f',"plan_sha256":"{plan.plan_sha256}"}}'
    extra = plan.as_dict()
    extra["host_path"] = "/"
    tampered = plan.as_dict()
    tampered["network"] = "bridge"

    with pytest.raises(ExecutionContractError, match="duplicate_json_key"):
        parse_execution_plan_json(duplicate)
    with pytest.raises(ExecutionContractError, match="plan_fields_invalid"):
        parse_execution_plan_json(json.dumps(extra))
    with pytest.raises(ExecutionContractError, match="isolation_policy_invalid"):
        parse_execution_plan_json(json.dumps(tampered))


def test_docker_arguments_enforce_all_m9_isolation_and_resource_controls() -> None:
    arguments = docker_create_arguments(_plan())
    joined = " ".join(arguments)

    assert "--network none" in joined
    assert "--read-only" in arguments
    assert "--user 65532:65532" in joined
    assert "--cap-drop ALL" in joined
    assert "no-new-privileges=true" in joined
    assert "--pids-limit 64" in joined
    assert "--memory 268435456" in joined
    assert "--memory-swap 268435456" in joined
    assert "--cpus 0.500" in joined
    assert "/workspace:rw,nosuid,nodev,noexec,size=67108864" in joined
    assert "/var/run/docker.sock" not in joined
    assert "RELEASEPROOF_HOST_SENTINEL" not in joined


def test_output_is_bounded_but_preserves_full_content_hash_and_size() -> None:
    raw = b"sentinel" * 20_000
    output = SafeOutputV1.capture(raw, limit=4_096)

    assert len(output.excerpt.encode()) == 4_096
    assert output.original_bytes == len(raw)
    assert output.truncated is True


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        (b"PermissionError: blocked", "permission_error"),
        (
            b"Error response from daemon: OCI runtime create failed: invalid argument",
            "invalid_argument",
        ),
        (
            b"Error response from daemon: failed to create shim task",
            "runtime_task_creation",
        ),
        (b"Error response from daemon: rejected", "docker_runtime_error"),
        (b"Traceback (most recent call last)", "python_error"),
        (b"arbitrary untrusted value", "nonzero_exit"),
    ],
)
def test_runner_failure_classification_never_exposes_raw_output(
    stderr: bytes, expected: str
) -> None:
    completed = subprocess.CompletedProcess(("docker",), returncode=1, stdout=b"", stderr=stderr)

    category = _classify_runner_failure(completed)

    assert category == expected
    assert stderr.decode() not in category


def test_ephemeral_ci_diagnostic_is_bounded_and_neutralizes_control_text() -> None:
    diagnostic = _safe_ephemeral_ci_diagnostic(
        b"Error response from daemon:\n\x1b[31minvalid\r\n" + b"x" * 4_096
    )

    assert diagnostic.startswith("Error response from daemon: ?[31minvalid")
    assert "\n" not in diagnostic
    assert "\r" not in diagnostic
    assert "\x1b" not in diagnostic
    assert len(diagnostic) == 512


def test_runner_rejection_keeps_diagnostic_separate_from_stable_code() -> None:
    rejection = RunnerRejectedError(
        "runner_result_invalid_runtime_task_creation",
        ephemeral_ci_diagnostic="bounded fixture-only detail",
    )

    assert rejection.code == "runner_result_invalid_runtime_task_creation"
    assert rejection.ephemeral_ci_diagnostic == "bounded fixture-only detail"
