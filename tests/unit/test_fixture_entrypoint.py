from __future__ import annotations

import sys

import pytest

from runner.fixture_image.entrypoint import _resolved_allowlisted_command


def test_allowlisted_command_resolves_python_without_requiring_path() -> None:
    file_path = "tests/generated/test_example.py"

    resolved = _resolved_allowlisted_command(["python", "-m", "pytest", "-q", file_path], file_path)

    assert resolved == [sys.executable, "-m", "pytest", "-q", file_path]


@pytest.mark.parametrize(
    "command",
    [
        ["/usr/local/bin/python", "-m", "pytest", "-q", "tests/generated/test_example.py"],
        ["python", "-m", "pytest", "tests/generated/test_example.py"],
        ["python", "-m", "pytest", "-q", "tests/generated/test_other.py"],
    ],
)
def test_allowlisted_command_rejects_any_plan_variation(command: list[str]) -> None:
    with pytest.raises(ValueError, match="command is not allowlisted"):
        _resolved_allowlisted_command(command, "tests/generated/test_example.py")
