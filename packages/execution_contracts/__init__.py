"""Framework-light, versioned contracts for the separate execution boundary."""

from packages.execution_contracts.contracts import (
    CONTROLLED_FIXTURE_TREE_SHA256,
    EXECUTION_PLAN_SCHEMA_VERSION,
    EXECUTION_RESULT_SCHEMA_VERSION,
    ExecutionContractError,
    ExecutionOutcome,
    ExecutionPlanV1,
    ExecutionResultV1,
    FixtureExecutionInputV1,
    HostProfile,
    ResourceLimitsV1,
    SafeOutputV1,
    compute_tree_sha256,
    parse_execution_plan_json,
    parse_execution_result_json,
)
from packages.execution_contracts.signing import sign_payload, verify_payload_signature

__all__ = [
    "CONTROLLED_FIXTURE_TREE_SHA256",
    "EXECUTION_PLAN_SCHEMA_VERSION",
    "EXECUTION_RESULT_SCHEMA_VERSION",
    "ExecutionContractError",
    "ExecutionOutcome",
    "ExecutionPlanV1",
    "ExecutionResultV1",
    "FixtureExecutionInputV1",
    "HostProfile",
    "ResourceLimitsV1",
    "SafeOutputV1",
    "compute_tree_sha256",
    "parse_execution_plan_json",
    "parse_execution_result_json",
    "sign_payload",
    "verify_payload_signature",
]
