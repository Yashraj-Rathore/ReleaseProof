from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from adapters.test_generation.python_fixture import build_new_test_patch
from packages.execution_contracts import (
    ExecutionOutcome,
    ExecutionPlanV1,
    FixtureExecutionInputV1,
    HostProfile,
    ResourceLimitsV1,
    compute_tree_sha256,
    sign_payload,
)
from runner.docker_cli import RunnerRejectedError, run_fixture_plan

pytestmark = [
    pytest.mark.sandbox,
    pytest.mark.skipif(
        os.environ.get("RUN_SANDBOX_INTEGRATION") != "1",
        reason="set RUN_SANDBOX_INTEGRATION=1 on an explicit disposable Linux Docker host",
    ),
]

FIXTURE_ROOT = Path("tests/fixtures/repositories/releaseproof_fixture")
SIGNING_KEY = b"m9-live-sandbox-signing-key-is-at-least-32-bytes"


def _image_digest() -> str:
    executable = shutil.which("docker")
    assert executable is not None
    completed = subprocess.run(  # noqa: S603
        (executable, "image", "inspect", "releaseproof-fixture-runner:m9", "--format", "{{.Id}}"),
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    value = completed.stdout.strip()
    assert value.startswith("sha256:")
    return value


def _case(
    content: str, *, name: str, timeout: int = 10
) -> tuple[ExecutionPlanV1, FixtureExecutionInputV1]:
    file_path = f"tests/generated/test_{name}.py"
    execution_input = FixtureExecutionInputV1(
        proposal_hash="a" * 64,
        file_path=file_path,
        patch=build_new_test_patch(file_path=file_path, content=content),
    )
    plan = ExecutionPlanV1(
        organization_id="00000000-0000-0000-0000-000000000001",
        repository_id="00000000-0000-0000-0000-000000000002",
        snapshot_id="00000000-0000-0000-0000-000000000003",
        checkout_sha="b" * 40,
        proposal_id="00000000-0000-0000-0000-000000000004",
        proposal_hash=execution_input.proposal_hash,
        proposal_input_sha256=execution_input.input_sha256,
        fixture_tree_sha256=compute_tree_sha256(FIXTURE_ROOT),
        image=f"releaseproof/fixture-runner@{_image_digest()}",
        commands=(("python", "-m", "pytest", "-q", file_path),),
        resources=ResourceLimitsV1(wall_time_seconds=timeout),
        host_profile=HostProfile.EPHEMERAL_CI_FIXTURE,
    )
    return plan, execution_input


def _run(plan: ExecutionPlanV1, execution_input: FixtureExecutionInputV1):  # type: ignore[no-untyped-def]
    return run_fixture_plan(
        plan=plan,
        execution_input=execution_input,
        plan_signature=sign_payload(plan.canonical_bytes(), key=SIGNING_KEY),
        signing_key=SIGNING_KEY,
        allow_ephemeral_ci_fixture=True,
    )


def _assert_no_runner_containers() -> None:
    executable = shutil.which("docker")
    assert executable is not None
    completed = subprocess.run(  # noqa: S603
        (
            executable,
            "ps",
            "--all",
            "--filter",
            "label=releaseproof.runner=m9-fixture-v1",
            "--format",
            "{{.ID}}",
        ),
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.stdout.strip() == ""


def test_live_fixture_runner_proves_isolation_resources_timeout_output_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RELEASEPROOF_HOST_SENTINEL", "must-never-enter-the-container")
    passing, passing_input = _case(
        "from fixture_app.pricing import calculate_total\n\n\n"
        "def test_total() -> None:\n"
        "    assert calculate_total(100, 5) == 105\n",
        name="m9_pass",
    )
    passed = _run(passing, passing_input)

    assert passed.outcome is ExecutionOutcome.PASSED
    assert passed.exit_code == 0
    assert passed.cleanup_succeeded is True
    assert all(dict(passed.isolation_checks).values())
    _assert_no_runner_containers()

    timing, timing_input = _case(
        "from fixture_app.probes import wait_forever\n\n\n"
        "def test_timeout() -> None:\n"
        "    wait_forever()\n",
        name="m9_timeout",
        timeout=2,
    )
    timed_out = _run(timing, timing_input)
    assert timed_out.outcome is ExecutionOutcome.TIMEOUT
    assert timed_out.timed_out is True
    assert timed_out.killed is True
    assert timed_out.cleanup_succeeded is True
    _assert_no_runner_containers()

    noisy, noisy_input = _case(
        "from fixture_app.probes import emit_output\n\n\n"
        "def test_output_limit() -> None:\n"
        "    emit_output()\n"
        "    raise AssertionError('replay captured output')\n",
        name="m9_output",
    )
    bounded = _run(noisy, noisy_input)
    assert bounded.outcome is ExecutionOutcome.FAILED
    assert bounded.stdout.truncated is True
    assert len(bounded.stdout.excerpt.encode()) <= noisy.resources.output_bytes
    _assert_no_runner_containers()

    with pytest.raises(RunnerRejectedError, match="plan_signature_invalid"):
        run_fixture_plan(
            plan=passing,
            execution_input=passing_input,
            plan_signature="0" * 64,
            signing_key=SIGNING_KEY,
            allow_ephemeral_ci_fixture=True,
        )
    _assert_no_runner_containers()
