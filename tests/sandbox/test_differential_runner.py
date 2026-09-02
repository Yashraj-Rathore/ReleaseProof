from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from adapters.test_generation.python_fixture import build_new_test_patch
from packages.execution_contracts import (
    BASE_FIXTURE_SHA,
    DifferentialOutcome,
    DifferentialPlanV1,
    FixtureExecutionInputV1,
    HostProfile,
    MutationOutcome,
    ResourceLimitsV1,
    WorkloadOutcome,
    sign_payload,
)
from runner.docker_cli import RunnerRejectedError, run_differential_plan

pytestmark = [
    pytest.mark.sandbox,
    pytest.mark.skipif(
        os.environ.get("RUN_SANDBOX_INTEGRATION") != "1",
        reason="set RUN_SANDBOX_INTEGRATION=1 on an explicit disposable Linux Docker host",
    ),
]

SIGNING_KEY = b"m10-live-sandbox-signing-key-is-at-least-32-bytes"
_REVISIONS = {
    "identical": BASE_FIXTURE_SHA,
    "probe_timeout": "082df2491655a5bff0452212476a2e40c6af40547",
    "tax_regression": "703143e8e75a685bd5385ec6f7e8016795451c8d",
}


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


def _case(variant: str, *, timeout: int = 10) -> tuple[DifferentialPlanV1, FixtureExecutionInputV1]:
    file_path = "tests/generated/test_m10_quote.py"
    content = (
        "from fixture_app.pricing import Decimal, total_with_tax\n\n\n"
        "def test_quote_tax() -> None:\n"
        "    assert total_with_tax(Decimal('100'), Decimal('0.13')) == Decimal('113.00')\n"
    )
    execution_input = FixtureExecutionInputV1(
        proposal_hash="a" * 64,
        file_path=file_path,
        patch=build_new_test_patch(file_path=file_path, content=content),
    )
    plan = DifferentialPlanV1(
        organization_id="00000000-0000-0000-0000-000000000001",
        repository_id="00000000-0000-0000-0000-000000000002",
        snapshot_id="00000000-0000-0000-0000-000000000003",
        execution_plan_id="00000000-0000-0000-0000-000000000004",
        execution_approval_id="00000000-0000-0000-0000-000000000005",
        execution_plan_sha256="b" * 64,
        proposal_hash=execution_input.proposal_hash,
        proposal_input_sha256=execution_input.input_sha256,
        base_sha=BASE_FIXTURE_SHA,
        candidate_sha=_REVISIONS[variant],
        candidate_variant=variant,
        image=f"releaseproof/fixture-runner@{_image_digest()}",
        resources=ResourceLimitsV1(wall_time_seconds=timeout),
        host_profile=HostProfile.EPHEMERAL_CI_FIXTURE,
    )
    return plan, execution_input


def _run(plan: DifferentialPlanV1, execution_input: FixtureExecutionInputV1):  # type: ignore[no-untyped-def]
    return run_differential_plan(
        plan=plan,
        execution_input=execution_input,
        plan_signature=sign_payload(plan.canonical_bytes(), key=SIGNING_KEY),
        signing_key=SIGNING_KEY,
        allow_ephemeral_ci_fixture=True,
    )


def test_live_differential_runner_replays_parity_mutations_masks_and_timeout() -> None:
    regression_plan, regression_input = _case("tax_regression")
    regression = _run(regression_plan, regression_input)

    assert regression.outcome is DifferentialOutcome.DIFFERENCE
    assert regression.base.outcome is WorkloadOutcome.PASSED
    assert regression.candidate.outcome is WorkloadOutcome.FAILED
    assert regression.differences == ("tests.outcome", "http.body")
    assert {item.mutation_id: item.outcome for item in regression.mutations} == {
        "negative_guard_removed": MutationOutcome.SURVIVED,
        "tax_rate_forced": MutationOutcome.KILLED,
    }
    assert regression.mutation_killed == 1
    assert regression.mutation_total == 2
    assert regression.cleanup_succeeded is True
    assert all(dict(regression.isolation_checks).values())

    identical_plan, identical_input = _case("identical")
    identical = _run(identical_plan, identical_input)
    assert identical.outcome is DifferentialOutcome.NO_DIFFERENCE
    assert identical.differences == ()

    timeout_plan, timeout_input = _case("probe_timeout", timeout=2)
    timeout = _run(timeout_plan, timeout_input)
    assert timeout.outcome is DifferentialOutcome.UNKNOWN
    assert timeout.candidate.outcome is WorkloadOutcome.TIMEOUT

    with pytest.raises(RunnerRejectedError, match="differential_plan_signature_invalid"):
        run_differential_plan(
            plan=regression_plan,
            execution_input=regression_input,
            plan_signature="0" * 64,
            signing_key=SIGNING_KEY,
            allow_ephemeral_ci_fixture=True,
        )
