"""Static-only adapter for the controlled ReleaseProof Python fixture."""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from packages.ai_core import (
    GeneratedTestProposalV1,
    ProposalGenerationMetadata,
    ProposalRisk,
)

PYTHON_FIXTURE_ADAPTER = "python-fixture"
PYTHON_FIXTURE_ADAPTER_VERSION = "python-fixture-v1"
STATIC_VALIDATION_VERSION = "python-fixture-static-v1"
_TEST_ROOT = PurePosixPath("tests/generated")
_HUNK_HEADER = re.compile(r"^@@ -0,0 \+1,(?P<count>[1-9][0-9]*) @@\n$")
_ALLOWED_IMPORT_ROOTS = {"fixture_app", "pytest"}
_FORBIDDEN_NAMES = {
    "__import__",
    "breakpoint",
    "compile",
    "delattr",
    "eval",
    "exec",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}
_FORBIDDEN_ATTRIBUTES = {
    "call",
    "check_call",
    "check_output",
    "connect",
    "execv",
    "main",
    "open",
    "popen",
    "putenv",
    "remove",
    "rename",
    "replace",
    "request",
    "rmdir",
    "run",
    "send",
    "setenv",
    "socket",
    "spawn",
    "system",
    "unlink",
    "urlopen",
    "write_bytes",
    "write_text",
}
_FORBIDDEN_NODES = (
    ast.AsyncFunctionDef,
    ast.Await,
    ast.ClassDef,
    ast.Delete,
    ast.Global,
    ast.Lambda,
    ast.Nonlocal,
    ast.Yield,
    ast.YieldFrom,
)


@dataclass(frozen=True, slots=True)
class StaticCheck:
    name: str
    passed: bool
    code: str

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "code": self.code}


@dataclass(frozen=True, slots=True)
class StaticValidationReport:
    valid: bool
    checks: tuple[StaticCheck, ...]
    content_sha256: str | None
    validator_version: str = STATIC_VALIDATION_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "validator_version": self.validator_version,
            "valid": self.valid,
            "content_sha256": self.content_sha256,
            "checks": [check.as_dict() for check in self.checks],
        }


def build_new_test_patch(*, file_path: str, content: str) -> str:
    """Build a canonical inert new-file patch; it is never applied here."""

    lines = content.splitlines(keepends=True)
    added = "".join(f"+{line}" for line in lines)
    return f"--- /dev/null\n+++ b/{file_path}\n@@ -0,0 +1,{len(lines)} @@\n{added}"


def _path_check(file_path: str) -> StaticCheck:
    path = PurePosixPath(file_path)
    valid = (
        "\\" not in file_path
        and not path.is_absolute()
        and ".." not in path.parts
        and path.parent == _TEST_ROOT
        and path.name.startswith("test_")
        and path.suffix == ".py"
        and file_path == path.as_posix()
    )
    return StaticCheck("path", valid, "path_allowed" if valid else "path_not_allowed")


def _extract_new_file(proposal: GeneratedTestProposalV1) -> tuple[str | None, StaticCheck]:
    lines = proposal.patch.splitlines(keepends=True)
    if len(lines) < 4:
        return None, StaticCheck("patch", False, "patch_structure_invalid")
    expected_target = f"+++ b/{proposal.file_path}\n"
    match = _HUNK_HEADER.fullmatch(lines[2])
    if lines[0] != "--- /dev/null\n" or lines[1] != expected_target or match is None:
        return None, StaticCheck("patch", False, "patch_must_add_one_declared_file")
    added_lines = lines[3:]
    if not added_lines or any(
        not line.startswith("+") or line.startswith("+++") for line in added_lines
    ):
        return None, StaticCheck("patch", False, "patch_contains_non_addition")
    if int(match.group("count")) != len(added_lines):
        return None, StaticCheck("patch", False, "patch_line_count_mismatch")
    content = "".join(line[1:] for line in added_lines)
    return content, StaticCheck("patch", True, "new_file_patch_valid")


def _format_check(content: str) -> StaticCheck:
    lines = content.splitlines(keepends=True)
    valid = (
        content.endswith("\n")
        and "\r" not in content
        and "\t" not in content
        and all(len(line.rstrip("\n")) <= 100 for line in lines)
        and all(line.rstrip("\n") == line.rstrip("\n").rstrip(" ") for line in lines)
    )
    return StaticCheck(
        "format",
        valid,
        "canonical_python_text" if valid else "format_policy_failed",
    )


def _parse_check(content: str) -> tuple[ast.Module | None, StaticCheck]:
    try:
        tree = ast.parse(content, filename="<generated-test>", mode="exec")
    except (SyntaxError, ValueError, RecursionError):
        return None, StaticCheck("parse", False, "python_syntax_invalid")
    return tree, StaticCheck("parse", True, "python_ast_valid")


def _is_none_annotation(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _type_shape_check(tree: ast.Module) -> StaticCheck:
    test_functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    top_level_allowed = all(
        isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef)) for node in tree.body
    )
    functions_valid = bool(test_functions) and all(
        function.name.startswith("test_")
        and not function.decorator_list
        and not function.args.args
        and not function.args.posonlyargs
        and not function.args.kwonlyargs
        and function.args.vararg is None
        and function.args.kwarg is None
        and not function.args.defaults
        and not function.args.kw_defaults
        and _is_none_annotation(function.returns)
        for function in test_functions
    )
    valid = top_level_allowed and functions_valid
    return StaticCheck(
        "type_shape",
        valid,
        "typed_test_functions_valid" if valid else "typed_test_function_contract_failed",
    )


def _safety_check(tree: ast.Module) -> StaticCheck:
    safe = True
    for node in ast.walk(tree):
        if isinstance(node, _FORBIDDEN_NODES):
            safe = False
            break
        if isinstance(node, ast.Import):
            if any(
                alias.name.split(".", maxsplit=1)[0] not in _ALLOWED_IMPORT_ROOTS
                for alias in node.names
            ):
                safe = False
                break
        elif isinstance(node, ast.ImportFrom):
            if (
                node.level != 0
                or node.module is None
                or node.module.split(".", maxsplit=1)[0] not in _ALLOWED_IMPORT_ROOTS
                or any(alias.name == "*" for alias in node.names)
            ):
                safe = False
                break
        elif (
            isinstance(node, ast.Name) and (node.id in _FORBIDDEN_NAMES or node.id.startswith("__"))
        ) or (
            isinstance(node, ast.Attribute)
            and (node.attr.startswith("__") or node.attr in _FORBIDDEN_ATTRIBUTES)
        ):
            safe = False
            break
    return StaticCheck(
        "safety",
        safe,
        "capabilities_within_fixture_allowlist" if safe else "forbidden_capability_detected",
    )


def _command_check(proposal: GeneratedTestProposalV1) -> StaticCheck:
    expected = (f"python -m pytest -q {proposal.file_path}",)
    valid = proposal.commands == expected
    return StaticCheck(
        "commands",
        valid,
        "fixture_command_allowlisted" if valid else "command_not_allowlisted",
    )


class PythonFixtureTestAdapter:
    adapter_name = PYTHON_FIXTURE_ADAPTER
    adapter_version = PYTHON_FIXTURE_ADAPTER_VERSION
    validator_version = STATIC_VALIDATION_VERSION

    def build_proposal(
        self,
        *,
        target_behavior: str,
        rationale: str,
        evidence_ids: tuple[str, ...],
        file_path: str,
        test_content: str,
        expected_result: str,
        risk: ProposalRisk,
        generation: ProposalGenerationMetadata,
    ) -> GeneratedTestProposalV1:
        """Create a typed, inert proposal for the controlled fixture adapter."""

        return GeneratedTestProposalV1(
            target_behavior=target_behavior,
            rationale=rationale,
            evidence_ids=evidence_ids,
            file_path=file_path,
            patch=build_new_test_patch(file_path=file_path, content=test_content),
            commands=(f"python -m pytest -q {file_path}",),
            expected_result=expected_result,
            risk=risk,
            test_adapter=self.adapter_name,
            test_adapter_version=self.adapter_version,
            generation=generation,
        )

    def validate(self, proposal: GeneratedTestProposalV1) -> StaticValidationReport:
        checks: list[StaticCheck] = []
        adapter_valid = (
            proposal.test_adapter == self.adapter_name
            and proposal.test_adapter_version == self.adapter_version
        )
        checks.append(
            StaticCheck(
                "adapter",
                adapter_valid,
                "adapter_supported" if adapter_valid else "adapter_not_supported",
            )
        )
        checks.append(_path_check(proposal.file_path))
        content, patch_check = _extract_new_file(proposal)
        checks.append(patch_check)
        checks.append(_command_check(proposal))
        if content is None:
            checks.extend(
                (
                    StaticCheck("format", False, "not_checked_without_valid_patch"),
                    StaticCheck("parse", False, "not_checked_without_valid_patch"),
                    StaticCheck("type_shape", False, "not_checked_without_valid_ast"),
                    StaticCheck("safety", False, "not_checked_without_valid_ast"),
                )
            )
            return StaticValidationReport(False, tuple(checks), None)
        checks.append(_format_check(content))
        tree, parse_check = _parse_check(content)
        checks.append(parse_check)
        if tree is None:
            checks.extend(
                (
                    StaticCheck("type_shape", False, "not_checked_without_valid_ast"),
                    StaticCheck("safety", False, "not_checked_without_valid_ast"),
                )
            )
        else:
            checks.append(_type_shape_check(tree))
            checks.append(_safety_check(tree))
        return StaticValidationReport(
            valid=all(check.passed for check in checks),
            checks=tuple(checks),
            content_sha256=hashlib.sha256(content.encode()).hexdigest(),
        )
