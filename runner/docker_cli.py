"""Docker CLI adapter for the accepted fixture-only execution boundary."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from dataclasses import replace

from packages.execution_contracts import (
    CONTROLLED_FIXTURE_TREE_SHA256,
    ExecutionContractError,
    ExecutionOutcome,
    ExecutionPlanV1,
    ExecutionResultV1,
    FixtureExecutionInputV1,
    HostProfile,
    SafeOutputV1,
    parse_execution_result_json,
    verify_payload_signature,
)


class RunnerRejectedError(RuntimeError):
    """A safe, stable runner-boundary rejection."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _classify_runner_failure(completed: subprocess.CompletedProcess[bytes]) -> str:
    """Return a bounded diagnostic category without exposing untrusted output."""

    stderr = completed.stderr[:196_608].lower()
    categories = (
        (b"read-only file system", "read_only_filesystem"),
        (b"permission denied", "permission_denied"),
        (b"permissionerror", "permission_error"),
        (b"no such file or directory", "file_not_found"),
        (b"filenotfounderror", "file_not_found"),
        (b"operation not permitted", "operation_not_permitted"),
        (b"invalid argument", "invalid_argument"),
        (b"no space left on device", "host_capacity"),
        (b"tmpfs", "tmpfs_configuration"),
        (b"memory.swap", "swap_configuration"),
        (b"cgroup", "cgroup_configuration"),
        (b"seccomp", "seccomp_configuration"),
        (b"apparmor", "lsm_configuration"),
        (b"failed to create shim task", "runtime_task_creation"),
        (b"failed to create task", "runtime_task_creation"),
        (b"unable to start container process", "container_process_start"),
        (b"error response from daemon", "docker_runtime_error"),
        (b"jsondecodeerror", "json_decode_error"),
        (b"assertionerror", "assertion_error"),
        (b"valueerror", "value_error"),
        (b"keyerror", "key_error"),
        (b"indexerror", "index_error"),
        (b"oserror", "os_error"),
        (b"traceback", "python_error"),
    )
    for marker, category in categories:
        if marker in stderr:
            return category
    if completed.returncode != 0:
        return "nonzero_exit"
    return "malformed_stdout"


def _docker(*args: str, timeout: int = 10) -> subprocess.CompletedProcess[bytes]:
    executable = shutil.which("docker")
    if executable is None:
        raise RunnerRejectedError("docker_unavailable")
    try:
        return subprocess.run(  # noqa: S603
            (executable, *args),
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise RunnerRejectedError("docker_unavailable") from error


def _validate_host(plan: ExecutionPlanV1, *, allow_ephemeral_ci_fixture: bool) -> None:
    info = _docker("info", "--format", "{{json .}}")
    if info.returncode != 0:
        raise RunnerRejectedError("docker_unavailable")
    try:
        payload = json.loads(info.stdout)
        operating_system = str(payload["OSType"])
        security = " ".join(str(value) for value in payload["SecurityOptions"])
        cgroup_version = str(payload["CgroupVersion"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RunnerRejectedError("docker_host_profile_invalid") from error
    lsm_enabled = "apparmor" in security or "selinux" in security
    if (
        operating_system != "linux"
        or cgroup_version != "2"
        or "seccomp" not in security
        or not lsm_enabled
    ):
        raise RunnerRejectedError("docker_host_profile_invalid")
    if plan.host_profile is HostProfile.DEDICATED_ROOTLESS_FIXTURE and "rootless" not in security:
        raise RunnerRejectedError("rootless_required")
    if plan.host_profile is HostProfile.EPHEMERAL_CI_FIXTURE and not allow_ephemeral_ci_fixture:
        raise RunnerRejectedError("ci_fixture_profile_not_enabled")


def _create_arguments(plan: ExecutionPlanV1, *, name: str) -> tuple[str, ...]:
    limits = plan.resources
    image_id = plan.image.split("@", maxsplit=1)[1]
    arguments = [
        "create",
        "--name",
        name,
        "--label",
        "releaseproof.runner=m9-fixture-v1",
        "--interactive",
        "--network",
        "none",
        "--read-only",
        "--user",
        "65532:65532",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--pids-limit",
        str(limits.pids),
        "--memory",
        str(limits.memory_bytes),
        "--memory-swap",
        str(limits.memory_bytes),
        "--cpus",
        f"{limits.cpu_millis / 1000:.3f}",
        "--ulimit",
        "nofile=128:128",
        "--tmpfs",
        (
            f"/workspace:rw,nosuid,nodev,noexec,size={limits.writable_tmpfs_bytes},uid=65532,gid=65532,mode=0700"
        ),
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=16777216,uid=65532,gid=65532,mode=0700",  # noqa: S108
        "--log-driver",
        "local",
        "--log-opt",
        "max-size=64k",
        "--log-opt",
        "max-file=1",
    ]
    for key, value in plan.environment:
        arguments.extend(("--env", f"{key}={value}"))
    arguments.append(image_id)
    return tuple(arguments)


def docker_create_arguments(
    plan: ExecutionPlanV1, *, name: str = "releaseproof-contract-test"
) -> tuple[str, ...]:
    """Expose deterministic arguments for policy/evaluation tests without executing Docker."""

    return _create_arguments(plan, name=name)


def _verify_container_security(name: str) -> None:
    inspected = _docker("inspect", name, "--format", "{{json .}}")
    if inspected.returncode != 0:
        raise RunnerRejectedError("container_inspect_failed")
    try:
        payload = json.loads(inspected.stdout)
        host_config = payload["HostConfig"]
        config = payload["Config"]
        safe = (
            host_config["NetworkMode"] == "none"
            and host_config["ReadonlyRootfs"] is True
            and host_config["Privileged"] is False
            and host_config["CapDrop"] == ["ALL"]
            and "no-new-privileges" in " ".join(host_config["SecurityOpt"])
            and config["User"] == "65532:65532"
            and not host_config["Binds"]
        )
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise RunnerRejectedError("container_inspect_failed") from error
    if not safe:
        raise RunnerRejectedError("container_policy_mismatch")


def run_fixture_plan(
    *,
    plan: ExecutionPlanV1,
    execution_input: FixtureExecutionInputV1,
    plan_signature: str,
    signing_key: bytes,
    attempt: int = 1,
    allow_ephemeral_ci_fixture: bool = False,
) -> ExecutionResultV1:
    """Verify and execute one exact fixture plan in a disposable hardened container."""

    if type(attempt) is not int or not 1 <= attempt <= 20:
        raise RunnerRejectedError("attempt_invalid")
    if not verify_payload_signature(
        plan.canonical_bytes(), signature=plan_signature, key=signing_key
    ):
        raise RunnerRejectedError("plan_signature_invalid")
    if execution_input.proposal_hash != plan.proposal_hash:
        raise RunnerRejectedError("proposal_hash_mismatch")
    if execution_input.input_sha256 != plan.proposal_input_sha256:
        raise RunnerRejectedError("proposal_input_hash_mismatch")
    _validate_host(plan, allow_ephemeral_ci_fixture=allow_ephemeral_ci_fixture)
    inspect_image = _docker(
        "image",
        "inspect",
        plan.image.split("@", maxsplit=1)[1],
        "--format",
        "{{json .Config.Labels}}",
    )
    if inspect_image.returncode != 0:
        raise RunnerRejectedError("image_digest_unavailable")
    try:
        labels = json.loads(inspect_image.stdout)
    except (TypeError, json.JSONDecodeError) as error:
        raise RunnerRejectedError("image_labels_invalid") from error
    if not isinstance(labels, dict) or (
        labels.get("org.releaseproof.fixture-tree-sha256") != CONTROLLED_FIXTURE_TREE_SHA256
        or labels.get("org.releaseproof.runner-version") != "releaseproof-fixture-runner-v1"
    ):
        raise RunnerRejectedError("image_labels_invalid")

    name = f"releaseproof-m9-{uuid.uuid4().hex}"
    created = False
    cleanup_succeeded = False
    result: ExecutionResultV1 | None = None
    started = time.monotonic()
    try:
        created_result = _docker(*_create_arguments(plan, name=name))
        if created_result.returncode != 0:
            raise RunnerRejectedError("container_create_failed")
        created = True
        _verify_container_security(name)
        payload = json.dumps(
            {"attempt": attempt, "input": execution_input.as_dict(), "plan": plan.as_dict()},
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        try:
            executable = shutil.which("docker")
            if executable is None:
                raise RunnerRejectedError("docker_unavailable")
            completed = subprocess.run(  # noqa: S603
                (executable, "start", "--attach", "--interactive", name),
                input=payload,
                check=False,
                capture_output=True,
                timeout=plan.resources.wall_time_seconds + 5,
            )
        except subprocess.TimeoutExpired:
            _docker("kill", name)
            empty = SafeOutputV1.capture(b"", limit=plan.resources.output_bytes)
            result = ExecutionResultV1(
                plan_sha256=plan.plan_sha256,
                image=plan.image,
                attempt=attempt,
                outcome=ExecutionOutcome.TIMEOUT,
                elapsed_milliseconds=int((time.monotonic() - started) * 1000),
                exit_code=None,
                stdout=empty,
                stderr=empty,
                timed_out=True,
                killed=True,
                cleanup_succeeded=False,
                isolation_checks=(("outer_timeout", True),),
            )
        else:
            if len(completed.stdout) > 196_608:
                raise RunnerRejectedError("runner_output_too_large")
            try:
                result = parse_execution_result_json(completed.stdout.decode("utf-8"))
            except (UnicodeDecodeError, ExecutionContractError) as error:
                category = _classify_runner_failure(completed)
                raise RunnerRejectedError(f"runner_result_invalid_{category}") from error
            if (
                result.plan_sha256 != plan.plan_sha256
                or result.image != plan.image
                or result.attempt != attempt
            ):
                raise RunnerRejectedError("runner_result_binding_invalid")
    finally:
        if created:
            removed = _docker("rm", "--force", name)
            cleanup_succeeded = removed.returncode == 0
    if result is None:
        raise RunnerRejectedError("runner_result_missing")
    return replace(result, cleanup_succeeded=cleanup_succeeded)
