"""Strict M10 fixture-only differential and mutation contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from uuid import UUID

from packages.execution_contracts.contracts import (
    ExecutionContractError,
    HostProfile,
    ResourceLimitsV1,
    SafeOutputV1,
    _exact_keys,
    _load_unique_json,
    _output,
    canonical_json_bytes,
    compute_tree_sha256,
    object_sha256,
)

DIFFERENTIAL_PLAN_SCHEMA_VERSION = "releaseproof.differential-plan.v1"
DIFFERENTIAL_RESULT_SCHEMA_VERSION = "releaseproof.differential-result.v1"
DIFFERENTIAL_RUNNER_VERSION = "releaseproof-differential-runner-v1"
DIFFERENTIAL_WORKLOAD_VERSION = "releaseproof.fixture-workload.v1"
NONDETERMINISM_MASK_VERSION = "releaseproof.fixture-mask.v1"
MUTATION_SET_VERSION = "releaseproof.fixture-mutations.v1"
DIFFERENTIAL_FIXTURE_BUNDLE_SHA256 = (
    "8e3554c97d41207213554f092e2bcb439560164ae0fcb744c5b56e6adf81f87e"
)
BASE_FIXTURE_SHA = "a043cc1f93e40f7f14c1de107a4364177ae25392"
_CANDIDATE_REVISIONS = {
    "identical": BASE_FIXTURE_SHA,
    "probe_timeout": "082df2491655a5bff0452212476a2e40c6af40547",
    "tax_regression": "703143e8e75a685bd5385ec6f7e8016795451c8d",
}
ALLOWED_MUTATIONS = ("negative_guard_removed", "tax_rate_forced")
ALLOWED_MASK_PATHS = ("http.headers.x-request-id", "state.updated_at")
_SAFE_ENVIRONMENT = (
    ("LANG", "C.UTF-8"),
    ("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1"),
    ("PYTHONDONTWRITEBYTECODE", "1"),
    ("PYTHONHASHSEED", "0"),
)
_IMAGE = re.compile(r"^releaseproof/fixture-runner@sha256:[0-9a-f]{64}$")
_LIMITATIONS = (
    "synthetic_fixture_only",
    "bounded_mutation_operators_not_exhaustive",
    "latency_is_descriptive_not_a_performance_regression_gate",
)


def compute_differential_bundle_sha256(root: Path) -> str:
    """Hash only executable base/overlay content; manifest metadata is not self-hashed."""

    return object_sha256(
        {
            "base": compute_tree_sha256(root / "base"),
            "overlays": {
                name: compute_tree_sha256(root / "overlays" / name)
                for name in ("negative_guard_removed", "probe_timeout", "tax_regression")
            },
        }
    )


class DifferentialOutcome(StrEnum):
    NO_DIFFERENCE = "no_difference"
    DIFFERENCE = "difference"
    BASE_FAILED = "base_failed"
    UNKNOWN = "unknown"


class WorkloadOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"


class MutationOutcome(StrEnum):
    KILLED = "killed"
    SURVIVED = "survived"
    INCONCLUSIVE = "inconclusive"


def _uuid(value: str) -> None:
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (AttributeError, TypeError, ValueError) as error:
        raise ExecutionContractError("differential_identifier_invalid") from error


def _sha256(value: str, code: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ExecutionContractError(code)


@dataclass(frozen=True, slots=True)
class DifferentialPlanV1:
    organization_id: str
    repository_id: str
    snapshot_id: str
    execution_plan_id: str
    execution_approval_id: str
    execution_plan_sha256: str
    proposal_hash: str
    proposal_input_sha256: str
    base_sha: str
    candidate_sha: str
    candidate_variant: str
    image: str
    resources: ResourceLimitsV1 = field(default_factory=ResourceLimitsV1)
    host_profile: HostProfile = HostProfile.DEDICATED_ROOTLESS_FIXTURE
    mutation_ids: tuple[str, ...] = ALLOWED_MUTATIONS
    mask_paths: tuple[str, ...] = ALLOWED_MASK_PATHS
    schema_version: str = DIFFERENTIAL_PLAN_SCHEMA_VERSION
    runner_version: str = DIFFERENTIAL_RUNNER_VERSION
    workload_version: str = DIFFERENTIAL_WORKLOAD_VERSION
    mask_policy_version: str = NONDETERMINISM_MASK_VERSION
    mutation_set_version: str = MUTATION_SET_VERSION
    fixture_bundle_sha256: str = DIFFERENTIAL_FIXTURE_BUNDLE_SHA256
    network: str = "none"
    mounts: tuple[str, ...] = ()
    environment: tuple[tuple[str, str], ...] = _SAFE_ENVIRONMENT

    def __post_init__(self) -> None:
        for identifier in (
            self.organization_id,
            self.repository_id,
            self.snapshot_id,
            self.execution_plan_id,
            self.execution_approval_id,
        ):
            _uuid(identifier)
        for value, code in (
            (self.execution_plan_sha256, "execution_plan_hash_invalid"),
            (self.proposal_hash, "proposal_hash_invalid"),
            (self.proposal_input_sha256, "proposal_input_hash_invalid"),
            (self.fixture_bundle_sha256, "differential_bundle_hash_invalid"),
        ):
            _sha256(value, code)
        if self.fixture_bundle_sha256 != DIFFERENTIAL_FIXTURE_BUNDLE_SHA256:
            raise ExecutionContractError("differential_bundle_not_allowed")
        if self.base_sha != BASE_FIXTURE_SHA:
            raise ExecutionContractError("differential_base_not_allowed")
        if _CANDIDATE_REVISIONS.get(self.candidate_variant) != self.candidate_sha:
            raise ExecutionContractError("differential_candidate_not_allowed")
        if _IMAGE.fullmatch(self.image) is None:
            raise ExecutionContractError("image_not_allowed")
        if (
            self.schema_version != DIFFERENTIAL_PLAN_SCHEMA_VERSION
            or self.runner_version != DIFFERENTIAL_RUNNER_VERSION
            or self.workload_version != DIFFERENTIAL_WORKLOAD_VERSION
            or self.mask_policy_version != NONDETERMINISM_MASK_VERSION
            or self.mutation_set_version != MUTATION_SET_VERSION
        ):
            raise ExecutionContractError("differential_version_unsupported")
        if self.network != "none" or self.mounts or self.environment != _SAFE_ENVIRONMENT:
            raise ExecutionContractError("isolation_policy_invalid")
        if (
            not self.mutation_ids
            or len(self.mutation_ids) > len(ALLOWED_MUTATIONS)
            or len(set(self.mutation_ids)) != len(self.mutation_ids)
            or not set(self.mutation_ids).issubset(ALLOWED_MUTATIONS)
        ):
            raise ExecutionContractError("mutation_set_invalid")
        if tuple(sorted(self.mask_paths)) != ALLOWED_MASK_PATHS:
            raise ExecutionContractError("mask_policy_invalid")

    def content_dict(self) -> dict[str, object]:
        return {
            "base_sha": self.base_sha,
            "candidate_sha": self.candidate_sha,
            "candidate_variant": self.candidate_variant,
            "environment": dict(self.environment),
            "execution_approval_id": self.execution_approval_id,
            "execution_plan_id": self.execution_plan_id,
            "execution_plan_sha256": self.execution_plan_sha256,
            "fixture_bundle_sha256": self.fixture_bundle_sha256,
            "host_profile": self.host_profile.value,
            "image": self.image,
            "mask_paths": list(self.mask_paths),
            "mask_policy_version": self.mask_policy_version,
            "mounts": list(self.mounts),
            "mutation_ids": list(self.mutation_ids),
            "mutation_set_version": self.mutation_set_version,
            "network": self.network,
            "organization_id": self.organization_id,
            "proposal_hash": self.proposal_hash,
            "proposal_input_sha256": self.proposal_input_sha256,
            "repository_id": self.repository_id,
            "resources": self.resources.as_dict(),
            "runner_version": self.runner_version,
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "workload_version": self.workload_version,
        }

    @property
    def plan_sha256(self) -> str:
        return object_sha256(self.content_dict())

    def as_dict(self) -> dict[str, object]:
        return {**self.content_dict(), "plan_sha256": self.plan_sha256}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.as_dict())


@dataclass(frozen=True, slots=True)
class WorkloadObservationV1:
    outcome: WorkloadOutcome
    test_exit_code: int | None
    test_elapsed_milliseconds: int
    probe_exit_code: int | None
    probe_elapsed_milliseconds: int
    http: dict[str, object] | None
    state: dict[str, object] | None
    events: tuple[dict[str, object], ...]
    stdout: SafeOutputV1
    stderr: SafeOutputV1

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, WorkloadOutcome):
            raise ExecutionContractError("workload_outcome_invalid")
        for elapsed in (self.test_elapsed_milliseconds, self.probe_elapsed_milliseconds):
            if type(elapsed) is not int or not 0 <= elapsed <= 120_000:
                raise ExecutionContractError("workload_timing_invalid")
        for exit_code in (self.test_exit_code, self.probe_exit_code):
            if exit_code is not None and (type(exit_code) is not int or not -1 <= exit_code <= 255):
                raise ExecutionContractError("workload_exit_code_invalid")
        if self.outcome is WorkloadOutcome.PASSED and (
            self.test_exit_code != 0 or self.probe_exit_code != 0 or self.http is None
        ):
            raise ExecutionContractError("passed_workload_invalid")
        if len(self.events) > 32:
            raise ExecutionContractError("workload_events_invalid")
        if self.http is not None:
            _exact_keys(
                self.http,
                {"body", "headers", "schema", "status"},
                "workload_http_invalid",
            )
            body = self.http["body"]
            headers = self.http["headers"]
            schema = self.http["schema"]
            status = self.http["status"]
            if (
                not isinstance(body, dict)
                or set(body) != {"currency", "total"}
                or not all(isinstance(item, str) and len(item) <= 32 for item in body.values())
                or not isinstance(headers, dict)
                or set(headers) - {"content-type", "x-request-id"}
                or not all(isinstance(item, str) and len(item) <= 128 for item in headers.values())
                or schema != {"currency": "string", "total": "string"}
                or type(status) is not int
                or not 100 <= status <= 599
            ):
                raise ExecutionContractError("workload_http_invalid")
        if self.state is not None and (
            set(self.state) != {"quote_count", "updated_at"}
            or type(self.state["quote_count"]) is not int
            or not 0 <= self.state["quote_count"] <= 1_000
            or not isinstance(self.state["updated_at"], str)
            or len(self.state["updated_at"]) > 64
        ):
            raise ExecutionContractError("workload_state_invalid")
        for event in self.events:
            if (
                not isinstance(event, dict)
                or set(event) != {"name", "sequence"}
                or not isinstance(event["name"], str)
                or len(event["name"]) > 128
                or type(event["sequence"]) is not int
                or not 0 <= event["sequence"] <= 1_000
            ):
                raise ExecutionContractError("workload_events_invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "events": list(self.events),
            "http": self.http,
            "outcome": self.outcome.value,
            "probe_elapsed_milliseconds": self.probe_elapsed_milliseconds,
            "probe_exit_code": self.probe_exit_code,
            "state": self.state,
            "stderr": self.stderr.as_dict(),
            "stdout": self.stdout.as_dict(),
            "test_elapsed_milliseconds": self.test_elapsed_milliseconds,
            "test_exit_code": self.test_exit_code,
        }


@dataclass(frozen=True, slots=True)
class MutationResultV1:
    mutation_id: str
    outcome: MutationOutcome
    elapsed_milliseconds: int
    exit_code: int | None

    def __post_init__(self) -> None:
        if self.mutation_id not in ALLOWED_MUTATIONS or not isinstance(
            self.outcome, MutationOutcome
        ):
            raise ExecutionContractError("mutation_result_invalid")
        if (
            type(self.elapsed_milliseconds) is not int
            or not 0 <= self.elapsed_milliseconds <= 120_000
        ):
            raise ExecutionContractError("mutation_result_invalid")
        if self.exit_code is not None and (
            type(self.exit_code) is not int or not -1 <= self.exit_code <= 255
        ):
            raise ExecutionContractError("mutation_result_invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "elapsed_milliseconds": self.elapsed_milliseconds,
            "exit_code": self.exit_code,
            "mutation_id": self.mutation_id,
            "outcome": self.outcome.value,
        }


def compare_observations(
    base: WorkloadObservationV1, candidate: WorkloadObservationV1
) -> tuple[DifferentialOutcome, tuple[str, ...]]:
    """Compare selected deterministic facts; configured masks never enter these projections."""

    if base.outcome is not WorkloadOutcome.PASSED:
        return DifferentialOutcome.BASE_FAILED, ()
    if candidate.outcome in {WorkloadOutcome.TIMEOUT, WorkloadOutcome.UNAVAILABLE}:
        return DifferentialOutcome.UNKNOWN, ()
    differences: list[str] = []
    if candidate.outcome is not WorkloadOutcome.PASSED:
        differences.append("tests.outcome")
    if base.http is not None and candidate.http is not None:
        if base.http.get("status") != candidate.http.get("status"):
            differences.append("http.status")
        if base.http.get("schema") != candidate.http.get("schema"):
            differences.append("http.schema")
        if base.http.get("body") != candidate.http.get("body"):
            differences.append("http.body")
    elif base.http != candidate.http:
        differences.append("http.missing")
    base_state = (
        {key: value for key, value in base.state.items() if key != "updated_at"}
        if base.state is not None
        else None
    )
    candidate_state = (
        {key: value for key, value in candidate.state.items() if key != "updated_at"}
        if candidate.state is not None
        else None
    )
    if base_state != candidate_state:
        differences.append("state.selected")
    if base.events != candidate.events:
        differences.append("events.selected")
    if differences:
        return DifferentialOutcome.DIFFERENCE, tuple(differences)
    return DifferentialOutcome.NO_DIFFERENCE, ()


@dataclass(frozen=True, slots=True)
class DifferentialResultV1:
    plan_sha256: str
    image: str
    attempt: int
    base: WorkloadObservationV1
    candidate: WorkloadObservationV1
    outcome: DifferentialOutcome
    differences: tuple[str, ...]
    mutations: tuple[MutationResultV1, ...]
    isolation_checks: tuple[tuple[str, bool], ...]
    cleanup_succeeded: bool
    limitations: tuple[str, ...] = _LIMITATIONS
    schema_version: str = DIFFERENTIAL_RESULT_SCHEMA_VERSION
    runner_version: str = DIFFERENTIAL_RUNNER_VERSION
    workload_version: str = DIFFERENTIAL_WORKLOAD_VERSION
    mask_policy_version: str = NONDETERMINISM_MASK_VERSION
    mutation_set_version: str = MUTATION_SET_VERSION

    def __post_init__(self) -> None:
        _sha256(self.plan_sha256, "differential_plan_hash_invalid")
        if _IMAGE.fullmatch(self.image) is None:
            raise ExecutionContractError("image_not_allowed")
        if type(self.attempt) is not int or not 1 <= self.attempt <= 20:
            raise ExecutionContractError("attempt_invalid")
        expected_outcome, expected_differences = compare_observations(self.base, self.candidate)
        if self.outcome is not expected_outcome or self.differences != expected_differences:
            raise ExecutionContractError("differential_comparison_invalid")
        if not self.mutations or len({item.mutation_id for item in self.mutations}) != len(
            self.mutations
        ):
            raise ExecutionContractError("mutation_results_invalid")
        checks = dict(self.isolation_checks)
        if not 1 <= len(checks) <= 20 or len(checks) != len(self.isolation_checks):
            raise ExecutionContractError("isolation_checks_invalid")
        if any(type(value) is not bool for value in checks.values()):
            raise ExecutionContractError("isolation_checks_invalid")
        if type(self.cleanup_succeeded) is not bool:
            raise ExecutionContractError("cleanup_invalid")
        if self.limitations != _LIMITATIONS:
            raise ExecutionContractError("differential_limitations_invalid")
        if (
            self.schema_version != DIFFERENTIAL_RESULT_SCHEMA_VERSION
            or self.runner_version != DIFFERENTIAL_RUNNER_VERSION
            or self.workload_version != DIFFERENTIAL_WORKLOAD_VERSION
            or self.mask_policy_version != NONDETERMINISM_MASK_VERSION
            or self.mutation_set_version != MUTATION_SET_VERSION
        ):
            raise ExecutionContractError("differential_result_version_invalid")

    @property
    def mutation_killed(self) -> int:
        return sum(item.outcome is MutationOutcome.KILLED for item in self.mutations)

    @property
    def mutation_total(self) -> int:
        return sum(item.outcome is not MutationOutcome.INCONCLUSIVE for item in self.mutations)

    def content_dict(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "base": self.base.as_dict(),
            "candidate": self.candidate.as_dict(),
            "cleanup_succeeded": self.cleanup_succeeded,
            "differences": list(self.differences),
            "image": self.image,
            "isolation_checks": dict(self.isolation_checks),
            "limitations": list(self.limitations),
            "mask_policy_version": self.mask_policy_version,
            "mutation_killed": self.mutation_killed,
            "mutation_set_version": self.mutation_set_version,
            "mutation_total": self.mutation_total,
            "mutations": [item.as_dict() for item in self.mutations],
            "outcome": self.outcome.value,
            "plan_sha256": self.plan_sha256,
            "runner_version": self.runner_version,
            "schema_version": self.schema_version,
            "workload_version": self.workload_version,
        }

    @property
    def result_sha256(self) -> str:
        return object_sha256(self.content_dict())

    def as_dict(self) -> dict[str, object]:
        return {**self.content_dict(), "result_sha256": self.result_sha256}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.as_dict())


def parse_differential_plan_json(raw: str) -> DifferentialPlanV1:
    value = _load_unique_json(raw, maximum_bytes=196_608)
    supplied_hash = value.pop("plan_sha256", None)
    expected = set(DifferentialPlanV1.__dataclass_fields__)
    _exact_keys(value, expected, "differential_plan_fields_invalid")
    try:
        plan = DifferentialPlanV1(
            **{
                **value,
                "environment": tuple(sorted(value["environment"].items())),
                "host_profile": HostProfile(value["host_profile"]),
                "mask_paths": tuple(value["mask_paths"]),
                "mounts": tuple(value["mounts"]),
                "mutation_ids": tuple(value["mutation_ids"]),
                "resources": ResourceLimitsV1.from_dict(value["resources"]),
            }
        )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        if isinstance(error, ExecutionContractError):
            raise
        raise ExecutionContractError("differential_plan_values_invalid") from error
    if supplied_hash != plan.plan_sha256:
        raise ExecutionContractError("differential_plan_hash_mismatch")
    return plan


def _observation(value: object) -> WorkloadObservationV1:
    if not isinstance(value, dict):
        raise ExecutionContractError("workload_observation_invalid")
    _exact_keys(
        value,
        {
            "events",
            "http",
            "outcome",
            "probe_elapsed_milliseconds",
            "probe_exit_code",
            "state",
            "stderr",
            "stdout",
            "test_elapsed_milliseconds",
            "test_exit_code",
        },
        "workload_observation_invalid",
    )
    try:
        return WorkloadObservationV1(
            **{
                **value,
                "events": tuple(value["events"]),
                "outcome": WorkloadOutcome(value["outcome"]),
                "stderr": _output(value["stderr"]),
                "stdout": _output(value["stdout"]),
            }
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ExecutionContractError):
            raise
        raise ExecutionContractError("workload_observation_invalid") from error


def parse_differential_result_json(raw: str) -> DifferentialResultV1:
    value = _load_unique_json(raw, maximum_bytes=393_216)
    supplied_hash = value.pop("result_sha256", None)
    expected = set(DifferentialResultV1.__dataclass_fields__) | {
        "mutation_killed",
        "mutation_total",
    }
    _exact_keys(value, expected, "differential_result_fields_invalid")
    supplied_killed = value.pop("mutation_killed")
    supplied_total = value.pop("mutation_total")
    try:
        checks = value["isolation_checks"]
        if not isinstance(checks, dict):
            raise ExecutionContractError("isolation_checks_invalid")
        result = DifferentialResultV1(
            **{
                **value,
                "base": _observation(value["base"]),
                "candidate": _observation(value["candidate"]),
                "differences": tuple(value["differences"]),
                "isolation_checks": tuple(sorted(checks.items())),
                "limitations": tuple(value["limitations"]),
                "mutations": tuple(
                    MutationResultV1(
                        mutation_id=item["mutation_id"],
                        outcome=MutationOutcome(item["outcome"]),
                        elapsed_milliseconds=item["elapsed_milliseconds"],
                        exit_code=item["exit_code"],
                    )
                    for item in value["mutations"]
                ),
                "outcome": DifferentialOutcome(value["outcome"]),
            }
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ExecutionContractError):
            raise
        raise ExecutionContractError("differential_result_values_invalid") from error
    if (
        supplied_hash != result.result_sha256
        or supplied_killed != result.mutation_killed
        or supplied_total != result.mutation_total
    ):
        raise ExecutionContractError("differential_result_hash_mismatch")
    return result
