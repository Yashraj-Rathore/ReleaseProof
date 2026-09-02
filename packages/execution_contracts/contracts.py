"""Strict immutable M9 execution-plan and execution-result contracts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

EXECUTION_PLAN_SCHEMA_VERSION = "releaseproof.execution-plan.v1"
EXECUTION_RESULT_SCHEMA_VERSION = "releaseproof.execution-result.v1"
RUNNER_VERSION = "releaseproof-fixture-runner-v1"
FIXTURE_ID = "releaseproof-fictional-python-v1"
CONTROLLED_FIXTURE_TREE_SHA256 = "70b1ebeb3d2257fa88667f06d8df3690de118dd277ec993f805d1851c17b4673"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CHECKOUT_SHA = re.compile(r"^[0-9a-f]{40}$")
_IMAGE = re.compile(r"^releaseproof/fixture-runner@sha256:[0-9a-f]{64}$")
_SAFE_ENV = {
    "LANG": "C.UTF-8",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "PYTHONHASHSEED": "0",
}
_EXPECTED_ARTIFACTS = ("runner-result-json-v1",)
_RESOURCE_FIELDS = {
    "cpu_millis",
    "memory_bytes",
    "output_bytes",
    "pids",
    "wall_time_seconds",
    "writable_tmpfs_bytes",
}


class ExecutionContractError(ValueError):
    """A safe, stable rejection at the execution trust boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class HostProfile(StrEnum):
    DEDICATED_ROOTLESS_FIXTURE = "dedicated-rootless-fixture-v1"
    EPHEMERAL_CI_FIXTURE = "ephemeral-ci-fixture-v1"


class ExecutionOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    KILLED = "killed"
    ISOLATION_FAILURE = "isolation_failure"
    RUNNER_UNAVAILABLE = "runner_unavailable"


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError) as error:
        raise ExecutionContractError("non_canonical_payload") from error


def object_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _exact_keys(value: dict[str, Any], expected: set[str], code: str) -> None:
    if set(value) != expected:
        raise ExecutionContractError(code)


def _checksum(value: object, code: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ExecutionContractError(code)


@dataclass(frozen=True, slots=True)
class ResourceLimitsV1:
    cpu_millis: int = 500
    memory_bytes: int = 268_435_456
    pids: int = 64
    wall_time_seconds: int = 15
    output_bytes: int = 65_536
    writable_tmpfs_bytes: int = 67_108_864

    def __post_init__(self) -> None:
        if not 100 <= self.cpu_millis <= 1_000:
            raise ExecutionContractError("cpu_limit_invalid")
        if not 134_217_728 <= self.memory_bytes <= 536_870_912:
            raise ExecutionContractError("memory_limit_invalid")
        if not 16 <= self.pids <= 128:
            raise ExecutionContractError("pid_limit_invalid")
        if not 2 <= self.wall_time_seconds <= 60:
            raise ExecutionContractError("timeout_invalid")
        if not 4_096 <= self.output_bytes <= 65_536:
            raise ExecutionContractError("output_limit_invalid")
        if not 16_777_216 <= self.writable_tmpfs_bytes <= 134_217_728:
            raise ExecutionContractError("disk_limit_invalid")

    def as_dict(self) -> dict[str, int]:
        return {
            "cpu_millis": self.cpu_millis,
            "memory_bytes": self.memory_bytes,
            "output_bytes": self.output_bytes,
            "pids": self.pids,
            "wall_time_seconds": self.wall_time_seconds,
            "writable_tmpfs_bytes": self.writable_tmpfs_bytes,
        }

    @classmethod
    def from_dict(cls, value: object) -> ResourceLimitsV1:
        if not isinstance(value, dict):
            raise ExecutionContractError("resources_invalid")
        _exact_keys(value, _RESOURCE_FIELDS, "resources_invalid")
        if any(type(item) is not int for item in value.values()):
            raise ExecutionContractError("resources_invalid")
        return cls(**value)


@dataclass(frozen=True, slots=True)
class FixtureExecutionInputV1:
    """The exact generated file content carried separately from the immutable plan."""

    proposal_hash: str
    file_path: str
    patch: str

    def __post_init__(self) -> None:
        _checksum(self.proposal_hash, "proposal_hash_invalid")
        if (
            not self.file_path.startswith("tests/generated/test_")
            or not self.file_path.endswith(".py")
            or ".." in self.file_path
            or "\\" in self.file_path
        ):
            raise ExecutionContractError("input_path_invalid")
        encoded = self.patch.encode("utf-8")
        if not 1 <= len(encoded) <= 65_536 or "\x00" in self.patch:
            raise ExecutionContractError("input_patch_invalid")

    def as_dict(self) -> dict[str, str]:
        return {
            "file_path": self.file_path,
            "patch": self.patch,
            "proposal_hash": self.proposal_hash,
        }

    @property
    def input_sha256(self) -> str:
        return object_sha256(self.as_dict())


@dataclass(frozen=True, slots=True)
class ExecutionPlanV1:
    organization_id: str
    repository_id: str
    snapshot_id: str
    checkout_sha: str
    proposal_id: str
    proposal_hash: str
    proposal_input_sha256: str
    fixture_tree_sha256: str
    image: str
    commands: tuple[tuple[str, ...], ...]
    resources: ResourceLimitsV1 = ResourceLimitsV1()
    host_profile: HostProfile = HostProfile.DEDICATED_ROOTLESS_FIXTURE
    schema_version: str = EXECUTION_PLAN_SCHEMA_VERSION
    fixture_id: str = FIXTURE_ID
    runner_version: str = RUNNER_VERSION
    network: str = "none"
    mounts: tuple[str, ...] = ()
    environment: tuple[tuple[str, str], ...] = tuple(sorted(_SAFE_ENV.items()))
    expected_artifacts: tuple[str, ...] = _EXPECTED_ARTIFACTS

    def __post_init__(self) -> None:
        if not isinstance(self.host_profile, HostProfile) or not isinstance(
            self.resources, ResourceLimitsV1
        ):
            raise ExecutionContractError("plan_types_invalid")
        if self.schema_version != EXECUTION_PLAN_SCHEMA_VERSION:
            raise ExecutionContractError("plan_schema_unsupported")
        if self.fixture_id != FIXTURE_ID or self.runner_version != RUNNER_VERSION:
            raise ExecutionContractError("runner_identity_invalid")
        if self.network != "none" or self.mounts:
            raise ExecutionContractError("isolation_policy_invalid")
        if dict(self.environment) != _SAFE_ENV or len(self.environment) != len(_SAFE_ENV):
            raise ExecutionContractError("environment_policy_invalid")
        if self.expected_artifacts != _EXPECTED_ARTIFACTS:
            raise ExecutionContractError("artifact_policy_invalid")
        if _IMAGE.fullmatch(self.image) is None:
            raise ExecutionContractError("image_not_allowed")
        if _CHECKOUT_SHA.fullmatch(self.checkout_sha) is None:
            raise ExecutionContractError("checkout_sha_invalid")
        for value, code in (
            (self.proposal_hash, "proposal_hash_invalid"),
            (self.proposal_input_sha256, "proposal_input_hash_invalid"),
            (self.fixture_tree_sha256, "fixture_tree_hash_invalid"),
        ):
            _checksum(value, code)
        if self.fixture_tree_sha256 != CONTROLLED_FIXTURE_TREE_SHA256:
            raise ExecutionContractError("fixture_tree_not_allowed")
        identifiers = (self.organization_id, self.repository_id, self.snapshot_id, self.proposal_id)
        try:
            if any(str(UUID(item)) != item for item in identifiers):
                raise ValueError
        except (AttributeError, TypeError, ValueError) as error:
            raise ExecutionContractError("identifier_invalid") from error
        if not 1 <= len(self.commands) <= 5:
            raise ExecutionContractError("commands_invalid")
        for command in self.commands:
            if command[:4] != ("python", "-m", "pytest", "-q") or len(command) != 5:
                raise ExecutionContractError("command_not_allowed")
            path = command[4]
            if not path.startswith("tests/generated/test_") or not path.endswith(".py"):
                raise ExecutionContractError("command_not_allowed")

    def content_dict(self) -> dict[str, object]:
        return {
            "checkout_sha": self.checkout_sha,
            "commands": [list(value) for value in self.commands],
            "environment": dict(self.environment),
            "expected_artifacts": list(self.expected_artifacts),
            "fixture_id": self.fixture_id,
            "fixture_tree_sha256": self.fixture_tree_sha256,
            "host_profile": self.host_profile.value,
            "image": self.image,
            "mounts": list(self.mounts),
            "network": self.network,
            "organization_id": self.organization_id,
            "proposal_hash": self.proposal_hash,
            "proposal_id": self.proposal_id,
            "proposal_input_sha256": self.proposal_input_sha256,
            "repository_id": self.repository_id,
            "resources": self.resources.as_dict(),
            "runner_version": self.runner_version,
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
        }

    @property
    def plan_sha256(self) -> str:
        return object_sha256(self.content_dict())

    def as_dict(self) -> dict[str, object]:
        return {**self.content_dict(), "plan_sha256": self.plan_sha256}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.as_dict())


@dataclass(frozen=True, slots=True)
class SafeOutputV1:
    excerpt: str
    sha256: str
    original_bytes: int
    truncated: bool

    def __post_init__(self) -> None:
        _checksum(self.sha256, "output_hash_invalid")
        if (
            not isinstance(self.excerpt, str)
            or type(self.original_bytes) is not int
            or self.original_bytes < 0
            or len(self.excerpt.encode("utf-8")) > 65_536
            or type(self.truncated) is not bool
        ):
            raise ExecutionContractError("output_invalid")

    @classmethod
    def capture(cls, raw: bytes, *, limit: int) -> SafeOutputV1:
        bounded = raw[:limit]
        return cls(
            excerpt=bounded.decode("utf-8", errors="replace"),
            sha256=hashlib.sha256(raw).hexdigest(),
            original_bytes=len(raw),
            truncated=len(raw) > limit,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "excerpt": self.excerpt,
            "original_bytes": self.original_bytes,
            "sha256": self.sha256,
            "truncated": self.truncated,
        }


@dataclass(frozen=True, slots=True)
class ExecutionResultV1:
    plan_sha256: str
    image: str
    attempt: int
    outcome: ExecutionOutcome
    elapsed_milliseconds: int
    exit_code: int | None
    stdout: SafeOutputV1
    stderr: SafeOutputV1
    timed_out: bool
    killed: bool
    cleanup_succeeded: bool
    isolation_checks: tuple[tuple[str, bool], ...]
    artifacts: tuple[str, ...] = _EXPECTED_ARTIFACTS
    schema_version: str = EXECUTION_RESULT_SCHEMA_VERSION
    runner_version: str = RUNNER_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ExecutionOutcome):
            raise ExecutionContractError("outcome_invalid")
        _checksum(self.plan_sha256, "plan_hash_invalid")
        if _IMAGE.fullmatch(self.image) is None:
            raise ExecutionContractError("image_not_allowed")
        if type(self.attempt) is not int or not 1 <= self.attempt <= 20:
            raise ExecutionContractError("attempt_invalid")
        if (
            type(self.elapsed_milliseconds) is not int
            or not 0 <= self.elapsed_milliseconds <= 120_000
        ):
            raise ExecutionContractError("result_timing_invalid")
        if self.exit_code is not None and (
            type(self.exit_code) is not int or not -1 <= self.exit_code <= 255
        ):
            raise ExecutionContractError("exit_code_invalid")
        if (
            self.schema_version != EXECUTION_RESULT_SCHEMA_VERSION
            or self.runner_version != RUNNER_VERSION
        ):
            raise ExecutionContractError("result_identity_invalid")
        if self.artifacts != _EXPECTED_ARTIFACTS:
            raise ExecutionContractError("result_artifacts_invalid")
        checks = dict(self.isolation_checks)
        if len(checks) != len(self.isolation_checks) or not 1 <= len(checks) <= 20:
            raise ExecutionContractError("isolation_checks_invalid")
        if self.outcome is ExecutionOutcome.PASSED and (
            not all(checks.values()) or self.exit_code != 0
        ):
            raise ExecutionContractError("passed_result_invalid")
        if self.timed_out != (self.outcome is ExecutionOutcome.TIMEOUT):
            raise ExecutionContractError("timeout_result_invalid")
        if self.outcome is ExecutionOutcome.TIMEOUT and not self.killed:
            raise ExecutionContractError("timeout_kill_invalid")
        if any(
            type(value) is not bool
            for value in (self.timed_out, self.killed, self.cleanup_succeeded)
        ):
            raise ExecutionContractError("result_flags_invalid")

    def content_dict(self) -> dict[str, object]:
        return {
            "artifacts": list(self.artifacts),
            "attempt": self.attempt,
            "cleanup_succeeded": self.cleanup_succeeded,
            "elapsed_milliseconds": self.elapsed_milliseconds,
            "exit_code": self.exit_code,
            "image": self.image,
            "isolation_checks": dict(self.isolation_checks),
            "killed": self.killed,
            "outcome": self.outcome.value,
            "plan_sha256": self.plan_sha256,
            "runner_version": self.runner_version,
            "schema_version": self.schema_version,
            "stderr": self.stderr.as_dict(),
            "stdout": self.stdout.as_dict(),
            "timed_out": self.timed_out,
        }

    @property
    def result_sha256(self) -> str:
        return object_sha256(self.content_dict())

    def as_dict(self) -> dict[str, object]:
        return {**self.content_dict(), "result_sha256": self.result_sha256}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.as_dict())


def _load_unique_json(raw: str, *, maximum_bytes: int) -> dict[str, Any]:
    if len(raw.encode("utf-8")) > maximum_bytes:
        raise ExecutionContractError("payload_too_large")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ExecutionContractError("duplicate_json_key")
            result[key] = value
        return result

    def reject_constant(_value: str) -> None:
        raise ValueError

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject_constant)
    except ExecutionContractError:
        raise
    except (json.JSONDecodeError, ValueError) as error:
        raise ExecutionContractError("invalid_json") from error
    if not isinstance(value, dict):
        raise ExecutionContractError("invalid_json_shape")
    return value


def parse_execution_plan_json(raw: str) -> ExecutionPlanV1:
    value = _load_unique_json(raw, maximum_bytes=131_072)
    expected = {
        "checkout_sha",
        "commands",
        "environment",
        "expected_artifacts",
        "fixture_id",
        "fixture_tree_sha256",
        "host_profile",
        "image",
        "mounts",
        "network",
        "organization_id",
        "plan_sha256",
        "proposal_hash",
        "proposal_id",
        "proposal_input_sha256",
        "repository_id",
        "resources",
        "runner_version",
        "schema_version",
        "snapshot_id",
    }
    _exact_keys(value, expected, "plan_fields_invalid")
    supplied_hash = value.pop("plan_sha256")
    try:
        plan = ExecutionPlanV1(
            organization_id=value["organization_id"],
            repository_id=value["repository_id"],
            snapshot_id=value["snapshot_id"],
            checkout_sha=value["checkout_sha"],
            proposal_id=value["proposal_id"],
            proposal_hash=value["proposal_hash"],
            proposal_input_sha256=value["proposal_input_sha256"],
            fixture_tree_sha256=value["fixture_tree_sha256"],
            image=value["image"],
            commands=tuple(tuple(item) for item in value["commands"]),
            resources=ResourceLimitsV1.from_dict(value["resources"]),
            host_profile=HostProfile(value["host_profile"]),
            schema_version=value["schema_version"],
            fixture_id=value["fixture_id"],
            runner_version=value["runner_version"],
            network=value["network"],
            mounts=tuple(value["mounts"]),
            environment=tuple(sorted(value["environment"].items())),
            expected_artifacts=tuple(value["expected_artifacts"]),
        )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        if isinstance(error, ExecutionContractError):
            raise
        raise ExecutionContractError("plan_values_invalid") from error
    if supplied_hash != plan.plan_sha256:
        raise ExecutionContractError("plan_hash_mismatch")
    return plan


def _output(value: object) -> SafeOutputV1:
    if not isinstance(value, dict):
        raise ExecutionContractError("output_invalid")
    _exact_keys(value, {"excerpt", "original_bytes", "sha256", "truncated"}, "output_invalid")
    try:
        return SafeOutputV1(**value)
    except TypeError as error:
        raise ExecutionContractError("output_invalid") from error


def parse_execution_result_json(raw: str) -> ExecutionResultV1:
    value = _load_unique_json(raw, maximum_bytes=196_608)
    expected = {
        "artifacts",
        "attempt",
        "cleanup_succeeded",
        "elapsed_milliseconds",
        "exit_code",
        "image",
        "isolation_checks",
        "killed",
        "outcome",
        "plan_sha256",
        "result_sha256",
        "runner_version",
        "schema_version",
        "stderr",
        "stdout",
        "timed_out",
    }
    _exact_keys(value, expected, "result_fields_invalid")
    supplied_hash = value.pop("result_sha256")
    try:
        checks = value["isolation_checks"]
        if not isinstance(checks, dict) or any(type(item) is not bool for item in checks.values()):
            raise ExecutionContractError("isolation_checks_invalid")
        result = ExecutionResultV1(
            plan_sha256=value["plan_sha256"],
            image=value["image"],
            attempt=value["attempt"],
            outcome=ExecutionOutcome(value["outcome"]),
            elapsed_milliseconds=value["elapsed_milliseconds"],
            exit_code=value["exit_code"],
            stdout=_output(value["stdout"]),
            stderr=_output(value["stderr"]),
            timed_out=value["timed_out"],
            killed=value["killed"],
            cleanup_succeeded=value["cleanup_succeeded"],
            isolation_checks=tuple(sorted(checks.items())),
            artifacts=tuple(value["artifacts"]),
            schema_version=value["schema_version"],
            runner_version=value["runner_version"],
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ExecutionContractError):
            raise
        raise ExecutionContractError("result_values_invalid") from error
    if supplied_hash != result.result_sha256:
        raise ExecutionContractError("result_hash_mismatch")
    return result


def compute_tree_sha256(root: Path) -> str:
    """Hash fixture paths/content without executing or importing repository code."""

    digest = hashlib.sha256()
    files = (
        item
        for item in root.rglob("*")
        if item.is_file()
        and "__pycache__" not in item.relative_to(root).parts
        and item.suffix != ".pyc"
        and not any(part.startswith(".") for part in item.relative_to(root).parts)
    )
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix().encode()):
        relative = path.relative_to(root).as_posix().encode()
        # Git normalizes these text fixtures to LF in CI; hash the same bytes on Windows.
        content = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()
