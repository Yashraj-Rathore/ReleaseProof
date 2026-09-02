"""Build or verify deterministic M9 contract/policy evidence (not live isolation evidence)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, cast

from packages.execution_contracts import (
    CONTROLLED_FIXTURE_TREE_SHA256,
    ExecutionPlanV1,
    FixtureExecutionInputV1,
    HostProfile,
    SafeOutputV1,
    compute_tree_sha256,
    sign_payload,
    verify_payload_signature,
)
from runner.docker_cli import docker_create_arguments

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "execution" / "m9_runner_cases_v1.json"
REPOSITORY_FIXTURE = ROOT / "tests" / "fixtures" / "repositories" / "releaseproof_fixture"
ARTIFACT_PATH = ROOT / "artifacts" / "evaluation" / "m9_runner_eval_v1.json"


def _json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _load_fixture() -> dict[str, Any]:
    value = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if (
        value.get("schema_version") != "m9-runner-evaluation-fixture-v1"
        or value.get("synthetic") is not True
    ):
        raise ValueError("M9 evaluation fixture identity is invalid")
    return cast(dict[str, Any], value)


def _plan() -> ExecutionPlanV1:
    execution_input = FixtureExecutionInputV1(
        proposal_hash="a" * 64,
        file_path="tests/generated/test_contract.py",
        patch=(
            "--- /dev/null\n+++ b/tests/generated/test_contract.py\n"
            "@@ -0,0 +1,2 @@\n+def test_contract() -> None:\n+    assert True\n"
        ),
    )
    return ExecutionPlanV1(
        organization_id="00000000-0000-0000-0000-000000000001",
        repository_id="00000000-0000-0000-0000-000000000002",
        snapshot_id="00000000-0000-0000-0000-000000000003",
        checkout_sha="b" * 40,
        proposal_id="00000000-0000-0000-0000-000000000004",
        proposal_hash=execution_input.proposal_hash,
        proposal_input_sha256=execution_input.input_sha256,
        fixture_tree_sha256=compute_tree_sha256(REPOSITORY_FIXTURE),
        image=f"releaseproof/fixture-runner@sha256:{'c' * 64}",
        commands=(("python", "-m", "pytest", "-q", execution_input.file_path),),
        host_profile=HostProfile.EPHEMERAL_CI_FIXTURE,
    )


def _artifact(fixture: dict[str, Any]) -> dict[str, object]:
    plan = _plan()
    arguments = docker_create_arguments(plan)
    joined = " ".join(arguments)
    key = b"m9-evaluation-signing-key-is-at-least-32-bytes"
    signature = sign_payload(plan.canonical_bytes(), key=key)
    output = SafeOutputV1.capture(b"x" * 100_000, limit=plan.resources.output_bytes)
    checks = {
        "cpu_memory_pid_disk_time_output_limits": all(
            item in joined
            for item in (
                "--cpus 0.500",
                "--memory 268435456",
                "--pids-limit 64",
                "/workspace:rw,nosuid,nodev,noexec,size=67108864",
            )
        )
        and output.truncated,
        "dropped_capabilities": "--cap-drop ALL" in joined,
        "immutable_plan_hash": len(plan.plan_sha256) == 64,
        "network_none": "--network none" in joined,
        "no_host_mounts": "/var/run/docker.sock" not in joined and not plan.mounts,
        "no_new_privileges": "no-new-privileges=true" in joined,
        "non_root": "--user 65532:65532" in joined,
        "pinned_image_digest": "@sha256:" in plan.image,
        "read_only_root": "--read-only" in arguments,
        "signed_boundary": verify_payload_signature(
            plan.canonical_bytes(), signature=signature, key=key
        )
        and not verify_payload_signature(
            plan.canonical_bytes() + b" ", signature=signature, key=key
        ),
    }
    expected = set(cast(list[str], fixture["expected_controls"]))
    return {
        "schema_version": "m9-runner-evaluation-v1",
        "synthetic": True,
        "fixture": {
            "path": FIXTURE_PATH.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(_json(fixture)).hexdigest(),
            "license": fixture["license"],
        },
        "controlled_repository": {
            "path": REPOSITORY_FIXTURE.relative_to(ROOT).as_posix(),
            "tree_sha256": plan.fixture_tree_sha256,
            "matches_frozen_hash": plan.fixture_tree_sha256 == CONTROLLED_FIXTURE_TREE_SHA256,
        },
        "quality": {
            "checks": checks,
            "expected_controls": sorted(expected),
            "all_expected_controls_present": set(checks) == expected,
            "all_checks_passed": all(checks.values()),
        },
        "decision": {
            "fixture_contract_and_policy_validated": all(checks.values())
            and set(checks) == expected,
            "live_container_sentinels_required_in_ci": True,
            "external_repository_execution_enabled": False,
        },
        "limitations": [
            "All inputs are synthetic and source controlled.",
            (
                "This stable artifact checks contracts and Docker arguments without executing "
                "a container."
            ),
            (
                "The sandbox-marked CI suite provides separate live sentinel evidence on a "
                "disposable host."
            ),
            "Neither evidence source justifies arbitrary external repository execution.",
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
            raise ValueError("committed M9 evaluation artifact is stale")
        print(json.dumps({"status": "verified", "all_checks_passed": True}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
