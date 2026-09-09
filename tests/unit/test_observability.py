from __future__ import annotations

import json
import logging
import uuid

import pytest

from packages.observability import (
    DEFAULT_QUOTA_LIMITS,
    DEFAULT_RETENTION_DAYS,
    OPERATIONAL_POLICY_SCHEMA_VERSION,
    FailureDisposition,
    canonical_policy_hash,
    correlation_scope,
    current_correlation_id,
    expected_failure_drills,
    validate_quota_limits,
    validate_retention_days,
)
from packages.observability.logging import SafeJsonFormatter


def test_operational_policy_contract_is_exact_bounded_and_hash_stable() -> None:
    quotas = validate_quota_limits(dict(DEFAULT_QUOTA_LIMITS))
    retention = validate_retention_days(dict(DEFAULT_RETENTION_DAYS))
    first = canonical_policy_hash(
        schema_version=OPERATIONAL_POLICY_SCHEMA_VERSION,
        version=1,
        quota_limits=quotas,
        retention_days=retention,
    )
    second = canonical_policy_hash(
        schema_version=OPERATIONAL_POLICY_SCHEMA_VERSION,
        version=1,
        quota_limits=dict(reversed(tuple(quotas.items()))),
        retention_days=dict(reversed(tuple(retention.items()))),
    )

    assert first == second
    assert len(first) == 64
    with pytest.raises(ValueError, match="exactly"):
        validate_quota_limits(quotas | {"unversioned_limit": 1})
    with pytest.raises(ValueError, match="integer"):
        validate_retention_days(dict(retention) | {"source_snapshot": True})


def test_correlation_scope_is_server_owned_and_restores_nested_context() -> None:
    outer = uuid.uuid4()
    inner = uuid.uuid4()

    with correlation_scope(outer):
        assert current_correlation_id() == outer
        with correlation_scope(inner):
            assert current_correlation_id() == inner
        assert current_correlation_id() == outer


def test_safe_json_formatter_drops_raw_message_and_secret_like_extras() -> None:
    record = logging.LogRecord(
        name="releaseproof.security",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="raw source password=must-not-appear",
        args=(),
        exc_info=None,
    )
    record.event = "request.denied"
    record.authorization = "Bearer must-not-appear"
    record.source = "private source must-not-appear"

    payload = SafeJsonFormatter().format(record)
    parsed = json.loads(payload)

    assert parsed["event"] == "request.denied"
    assert parsed["logger"] == "releaseproof.security"
    assert "must-not-appear" not in payload
    assert "authorization" not in payload
    assert "source" not in payload


def test_failure_drill_matrix_never_allows_false_ship() -> None:
    drills = expected_failure_drills()

    assert len(drills) == 7
    assert not any(drill.false_ship_possible for drill in drills)
    assert drills[-1].expected_disposition is FailureDisposition.UNKNOWN
