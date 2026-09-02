from __future__ import annotations

import json
from dataclasses import replace

import pytest

from adapters.test_generation import PythonFixtureTestAdapter
from adapters.test_generation.python_fixture import build_new_test_patch
from packages.ai_core import (
    TEST_PROPOSAL_JSON_SCHEMA,
    TEST_PROPOSAL_SCHEMA_SHA256,
    ProposalSchemaError,
    parse_test_proposal_json,
)
from tests.proposal_fixtures import VALID_TEST_PATH, proposal_fixture


def _codes(proposal: object) -> dict[str, bool]:
    report = PythonFixtureTestAdapter().validate(proposal)  # type: ignore[arg-type]
    return {check.name: check.passed for check in report.checks}


def test_strict_proposal_schema_and_hash_are_deterministic() -> None:
    proposal = proposal_fixture()
    raw = json.dumps(proposal.as_dict(), sort_keys=True)

    parsed = parse_test_proposal_json(raw)

    assert parsed == proposal
    assert parsed.proposal_sha256 == proposal.proposal_sha256
    assert len(TEST_PROPOSAL_SCHEMA_SHA256) == 64
    assert TEST_PROPOSAL_JSON_SCHEMA["additionalProperties"] is False


def test_strict_proposal_parser_rejects_extra_duplicate_and_unknown_risk() -> None:
    payload = proposal_fixture().as_dict()
    payload["authority"] = "execute"
    with pytest.raises(ProposalSchemaError):
        parse_test_proposal_json(json.dumps(payload))


def test_typed_proposal_constructor_rejects_runtime_type_coercion() -> None:
    proposal = proposal_fixture()

    with pytest.raises(ValueError, match="ProposalRisk"):
        replace(proposal, risk="medium")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tuple"):
        replace(proposal, evidence_ids=["evidence:fixture:pricing"])  # type: ignore[arg-type]

    raw = json.dumps(proposal_fixture().as_dict())
    duplicate = raw.replace(
        '"schema_version": "generated-test-proposal-v1",',
        '"schema_version": "generated-test-proposal-v1", '
        '"schema_version": "generated-test-proposal-v1",',
    )
    with pytest.raises(ProposalSchemaError):
        parse_test_proposal_json(duplicate)

    payload = proposal_fixture().as_dict()
    payload["risk"] = "execute_now"
    with pytest.raises(ProposalSchemaError):
        parse_test_proposal_json(json.dumps(payload))


def test_python_fixture_adapter_accepts_only_canonical_inert_new_test() -> None:
    proposal = proposal_fixture()
    report = PythonFixtureTestAdapter().validate(proposal)

    assert report.valid is True
    assert report.content_sha256 is not None
    assert all(check.passed for check in report.checks)
    assert [check.name for check in report.checks] == [
        "adapter",
        "path",
        "patch",
        "commands",
        "format",
        "parse",
        "type_shape",
        "safety",
    ]


@pytest.mark.parametrize(
    ("file_path", "commands"),
    [
        ("../src/fixture_app/service.py", None),
        ("src/fixture_app/test_backdoor.py", None),
        (VALID_TEST_PATH, ("powershell -Command whoami",)),
    ],
)
def test_path_and_command_allowlists_reject_scope_widening(
    file_path: str,
    commands: tuple[str, ...] | None,
) -> None:
    content = "def test_safe() -> None:\n    assert True\n"
    proposal = proposal_fixture(
        file_path=file_path,
        patch=build_new_test_patch(file_path=file_path, content=content),
        commands=commands,
    )
    checks = _codes(proposal)

    assert not checks["path"] or not checks["commands"]


@pytest.mark.parametrize(
    ("content", "failed_check"),
    [
        ("def test_broken( -> None:\n    pass\n", "parse"),
        ("def test_untyped():\n    assert True\n", "type_shape"),
        ("value = 1\n\ndef test_top_level() -> None:\n    assert value\n", "type_shape"),
        ("import os\n\ndef test_escape() -> None:\n    os.system('whoami')\n", "safety"),
        ("def test_read_secret() -> None:\n    assert open('.env').read()\n", "safety"),
        ("def test_dunder() -> None:\n    assert object().__class__\n", "safety"),
        ("def test_tabs() -> None:\n\tassert True\n", "format"),
    ],
)
def test_static_validation_rejects_malformed_or_capability_seeking_code(
    content: str,
    failed_check: str,
) -> None:
    proposal = proposal_fixture(
        patch=build_new_test_patch(file_path=VALID_TEST_PATH, content=content)
    )
    checks = _codes(proposal)

    assert checks[failed_check] is False
    assert PythonFixtureTestAdapter().validate(proposal).valid is False


def test_patch_parser_rejects_modification_or_mismatched_target() -> None:
    modified = (
        f"--- a/{VALID_TEST_PATH}\n"
        f"+++ b/{VALID_TEST_PATH}\n"
        "@@ -1,1 +1,1 @@\n"
        "-assert False\n"
        "+assert True\n"
    )
    mismatched = build_new_test_patch(
        file_path="tests/generated/test_other.py",
        content="def test_other() -> None:\n    assert True\n",
    )

    assert _codes(proposal_fixture(patch=modified))["patch"] is False
    assert _codes(proposal_fixture(patch=mismatched))["patch"] is False
