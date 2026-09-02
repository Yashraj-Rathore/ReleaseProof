from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from packages.execution_contracts import (
    BASE_FIXTURE_SHA,
    DifferentialOutcome,
    DifferentialPlanV1,
    DifferentialResultV1,
    ExecutionContractError,
    FixtureExecutionInputV1,
    HostProfile,
    MutationOutcome,
    MutationResultV1,
    SafeOutputV1,
    WorkloadObservationV1,
    WorkloadOutcome,
    compare_observations,
    compute_differential_bundle_sha256,
    parse_differential_plan_json,
    parse_differential_result_json,
)
from runner.docker_cli import docker_create_arguments
from runner.fixture_image.differential_entrypoint import _compare


def _input() -> FixtureExecutionInputV1:
    return FixtureExecutionInputV1(
        proposal_hash="a" * 64,
        file_path="tests/generated/test_quote.py",
        patch=(
            "--- /dev/null\n+++ b/tests/generated/test_quote.py\n"
            "@@ -0,0 +1,5 @@\n"
            "+from decimal import Decimal\n"
            "+from fixture_app.pricing import total_with_tax\n+\n"
            "+def test_quote() -> None:\n"
            "+    assert total_with_tax(Decimal('100'), Decimal('0.13')) == Decimal('113.00')\n"
        ),
    )


def _plan(
    *, variant: str = "tax_regression", candidate_sha: str | None = None
) -> DifferentialPlanV1:
    execution_input = _input()
    revisions = {
        "identical": BASE_FIXTURE_SHA,
        "probe_timeout": "082df2491655a5bff0452212476a2e40c6af40547",
        "tax_regression": "703143e8e75a685bd5385ec6f7e8016795451c8d",
    }
    return DifferentialPlanV1(
        organization_id="00000000-0000-0000-0000-000000000001",
        repository_id="00000000-0000-0000-0000-000000000002",
        snapshot_id="00000000-0000-0000-0000-000000000003",
        execution_plan_id="00000000-0000-0000-0000-000000000004",
        execution_approval_id="00000000-0000-0000-0000-000000000005",
        execution_plan_sha256="b" * 64,
        proposal_hash=execution_input.proposal_hash,
        proposal_input_sha256=execution_input.input_sha256,
        base_sha=BASE_FIXTURE_SHA,
        candidate_sha=candidate_sha or revisions[variant],
        candidate_variant=variant,
        image=f"releaseproof/fixture-runner@sha256:{'c' * 64}",
        host_profile=HostProfile.EPHEMERAL_CI_FIXTURE,
    )


def _observation(
    *, outcome: WorkloadOutcome = WorkloadOutcome.PASSED, total: str = "113.00"
) -> WorkloadObservationV1:
    empty = SafeOutputV1.capture(b"", limit=4_096)
    return WorkloadObservationV1(
        outcome=outcome,
        test_exit_code=0 if outcome is WorkloadOutcome.PASSED else 1,
        test_elapsed_milliseconds=10,
        probe_exit_code=0,
        probe_elapsed_milliseconds=2,
        http={
            "body": {"currency": "CAD", "total": total},
            "headers": {"content-type": "application/json", "x-request-id": "one"},
            "schema": {"currency": "string", "total": "string"},
            "status": 200,
        },
        state={"quote_count": 1, "updated_at": "one"},
        events=({"name": "quote.calculated", "sequence": 1},),
        stdout=empty,
        stderr=empty,
    )


def test_differential_contracts_round_trip_and_bind_every_parity_input() -> None:
    plan = _plan()
    base = _observation()
    candidate = _observation(outcome=WorkloadOutcome.FAILED, total="115.00")
    outcome, differences = compare_observations(base, candidate)
    result = DifferentialResultV1(
        plan_sha256=plan.plan_sha256,
        image=plan.image,
        attempt=1,
        base=base,
        candidate=candidate,
        outcome=outcome,
        differences=differences,
        mutations=(
            MutationResultV1("tax_rate_forced", MutationOutcome.KILLED, 8, 1),
            MutationResultV1("negative_guard_removed", MutationOutcome.SURVIVED, 7, 0),
        ),
        isolation_checks=(("fixture_boundary", True),),
        cleanup_succeeded=True,
    )

    assert parse_differential_plan_json(plan.canonical_bytes().decode()) == plan
    assert parse_differential_result_json(result.canonical_bytes().decode()) == result
    assert result.outcome is DifferentialOutcome.DIFFERENCE
    assert result.differences == ("tests.outcome", "http.body")
    assert result.mutation_killed == 1
    assert result.mutation_total == 2
    assert (
        plan.plan_sha256
        != replace(plan, candidate_variant="identical", candidate_sha=BASE_FIXTURE_SHA).plan_sha256
    )
    assert (
        compute_differential_bundle_sha256(Path("tests/fixtures/differential/releaseproof_m10"))
        == plan.fixture_bundle_sha256
    )


def test_contract_rejects_uncontrolled_sha_and_payload_tampering() -> None:
    with pytest.raises(ExecutionContractError, match="differential_candidate_not_allowed"):
        _plan(candidate_sha="d" * 40)

    raw = _plan().as_dict()
    raw["network"] = "bridge"
    with pytest.raises(ExecutionContractError, match="isolation_policy_invalid"):
        parse_differential_plan_json(json.dumps(raw))


def test_identical_observations_do_not_invent_regression_and_masks_are_explicit() -> None:
    base = _observation()
    candidate = replace(
        base,
        http={**(base.http or {}), "headers": {"x-request-id": "different"}},
        state={"quote_count": 1, "updated_at": "different"},
    )

    assert compare_observations(base, candidate) == (DifferentialOutcome.NO_DIFFERENCE, ())
    raw_base = base.as_dict()
    raw_candidate = candidate.as_dict()
    assert _compare(raw_base, raw_candidate) == ("no_difference", [])


def test_timeout_is_unknown_and_base_failure_does_not_blame_candidate() -> None:
    base = _observation()
    timeout = replace(
        _observation(outcome=WorkloadOutcome.FAILED),
        outcome=WorkloadOutcome.TIMEOUT,
        test_exit_code=None,
    )
    failed_base = _observation(outcome=WorkloadOutcome.FAILED)

    assert compare_observations(base, timeout) == (DifferentialOutcome.UNKNOWN, ())
    assert compare_observations(failed_base, base) == (DifferentialOutcome.BASE_FAILED, ())


def test_differential_plan_reuses_m9_isolation_controls() -> None:
    arguments = docker_create_arguments(_plan())
    joined = " ".join(arguments)

    assert "--network none" in joined
    assert "--read-only" in arguments
    assert "--user 65532:65532" in joined
    assert "--cap-drop ALL" in joined
    assert "no-new-privileges=true" in joined
    assert "/var/run/docker.sock" not in joined
