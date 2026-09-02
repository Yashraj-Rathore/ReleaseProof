"""Strict provider-neutral generated-test proposal contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, NoReturn, cast

TEST_PROPOSAL_SCHEMA_VERSION = "generated-test-proposal-v1"
_SCHEMA_PATH = Path(__file__).with_name("schemas") / "generated_test_proposal_v1.json"
_SCHEMA_BYTES = _SCHEMA_PATH.read_bytes()
TEST_PROPOSAL_SCHEMA_SHA256 = hashlib.sha256(_SCHEMA_BYTES).hexdigest()
TEST_PROPOSAL_JSON_SCHEMA = cast(dict[str, Any], json.loads(_SCHEMA_BYTES))
MAX_TEST_PROPOSAL_BYTES = 96 * 1024


class ProposalSchemaError(ValueError):
    """Generated proposal output is malformed or outside its strict contract."""


class ProposalRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def _identifier(value: str, *, field: str, maximum: int = 160) -> None:
    if not isinstance(value, str) or not value or len(value) > maximum or not value.isascii():
        raise ValueError(f"{field} must be a bounded ASCII identifier")
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"{field} contains control characters")


def _text(value: str, *, field: str, maximum_bytes: int) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > maximum_bytes
        or "\x00" in value
    ):
        raise ValueError(f"{field} must be non-empty and at most {maximum_bytes} UTF-8 bytes")


def _sha256(value: str, *, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class ProposalGenerationMetadata:
    provider_name: str
    model_id: str
    provider_adapter_version: str
    prompt_version: str
    prompt_sha256: str
    source_evidence_id: str

    def __post_init__(self) -> None:
        _identifier(self.provider_name, field="provider_name", maximum=128)
        _identifier(self.model_id, field="model_id")
        _identifier(
            self.provider_adapter_version,
            field="provider_adapter_version",
            maximum=64,
        )
        _identifier(self.prompt_version, field="prompt_version", maximum=64)
        _sha256(self.prompt_sha256, field="prompt_sha256")
        _identifier(self.source_evidence_id, field="source_evidence_id")

    def as_dict(self) -> dict[str, str]:
        return {
            "provider_name": self.provider_name,
            "model_id": self.model_id,
            "provider_adapter_version": self.provider_adapter_version,
            "prompt_version": self.prompt_version,
            "prompt_sha256": self.prompt_sha256,
            "source_evidence_id": self.source_evidence_id,
        }


@dataclass(frozen=True, slots=True)
class GeneratedTestProposalV1:
    target_behavior: str
    rationale: str
    evidence_ids: tuple[str, ...]
    file_path: str
    patch: str
    commands: tuple[str, ...]
    expected_result: str
    risk: ProposalRisk
    test_adapter: str
    test_adapter_version: str
    generation: ProposalGenerationMetadata
    schema_version: str = TEST_PROPOSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.risk, ProposalRisk):
            raise ValueError("risk must use the ProposalRisk vocabulary")
        if not isinstance(self.generation, ProposalGenerationMetadata):
            raise ValueError("generation must use ProposalGenerationMetadata")
        if self.schema_version != TEST_PROPOSAL_SCHEMA_VERSION:
            raise ValueError("test proposal schema version is unsupported")
        _text(self.target_behavior, field="target_behavior", maximum_bytes=500)
        _text(self.rationale, field="rationale", maximum_bytes=2_000)
        if (
            not isinstance(self.evidence_ids, tuple)
            or not self.evidence_ids
            or len(self.evidence_ids) > 50
            or len(set(self.evidence_ids)) != len(self.evidence_ids)
        ):
            raise ValueError("evidence_ids must be a bounded unique non-empty tuple")
        for evidence_id in self.evidence_ids:
            _identifier(evidence_id, field="evidence_id")
        _text(self.file_path, field="file_path", maximum_bytes=240)
        _text(self.patch, field="patch", maximum_bytes=65_536)
        if (
            not isinstance(self.commands, tuple)
            or not self.commands
            or len(self.commands) > 5
            or len(set(self.commands)) != len(self.commands)
        ):
            raise ValueError("commands must be a bounded unique non-empty tuple")
        for command in self.commands:
            _text(command, field="command", maximum_bytes=500)
        _text(self.expected_result, field="expected_result", maximum_bytes=1_000)
        _identifier(self.test_adapter, field="test_adapter", maximum=64)
        _identifier(self.test_adapter_version, field="test_adapter_version", maximum=64)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "target_behavior": self.target_behavior,
            "rationale": self.rationale,
            "evidence_ids": list(self.evidence_ids),
            "file_path": self.file_path,
            "patch": self.patch,
            "commands": list(self.commands),
            "expected_result": self.expected_result,
            "risk": self.risk.value,
            "test_adapter": self.test_adapter,
            "test_adapter_version": self.test_adapter_version,
            "generation": self.generation.as_dict(),
        }

    @property
    def proposal_sha256(self) -> str:
        encoded = json.dumps(
            self.as_dict(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


_ROOT_KEYS = {
    "schema_version",
    "target_behavior",
    "rationale",
    "evidence_ids",
    "file_path",
    "patch",
    "commands",
    "expected_result",
    "risk",
    "test_adapter",
    "test_adapter_version",
    "generation",
}
_GENERATION_KEYS = {
    "provider_name",
    "model_id",
    "provider_adapter_version",
    "prompt_version",
    "prompt_sha256",
    "source_evidence_id",
}


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object keys are forbidden")
        result[key] = value
    return result


def _object(value: object, *, keys: set[str], field: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ProposalSchemaError(f"{field} has an invalid object shape")
    return cast(dict[str, object], value)


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ProposalSchemaError(f"{field} must be a string")
    return value


def _strings(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ProposalSchemaError(f"{field} must be a string array")
    return tuple(value)


def parse_test_proposal_json(raw_output: str) -> GeneratedTestProposalV1:
    if len(raw_output.encode("utf-8")) > MAX_TEST_PROPOSAL_BYTES:
        raise ProposalSchemaError("test proposal output exceeds the byte limit")
    try:
        decoded = json.loads(
            raw_output,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
        root = _object(decoded, keys=_ROOT_KEYS, field="test proposal")
        generation_data = _object(
            root["generation"],
            keys=_GENERATION_KEYS,
            field="generation",
        )
        generation = ProposalGenerationMetadata(
            provider_name=_string(generation_data["provider_name"], field="provider_name"),
            model_id=_string(generation_data["model_id"], field="model_id"),
            provider_adapter_version=_string(
                generation_data["provider_adapter_version"],
                field="provider_adapter_version",
            ),
            prompt_version=_string(generation_data["prompt_version"], field="prompt_version"),
            prompt_sha256=_string(generation_data["prompt_sha256"], field="prompt_sha256"),
            source_evidence_id=_string(
                generation_data["source_evidence_id"],
                field="source_evidence_id",
            ),
        )
        return GeneratedTestProposalV1(
            schema_version=_string(root["schema_version"], field="schema_version"),
            target_behavior=_string(root["target_behavior"], field="target_behavior"),
            rationale=_string(root["rationale"], field="rationale"),
            evidence_ids=_strings(root["evidence_ids"], field="evidence_ids"),
            file_path=_string(root["file_path"], field="file_path"),
            patch=_string(root["patch"], field="patch"),
            commands=_strings(root["commands"], field="commands"),
            expected_result=_string(root["expected_result"], field="expected_result"),
            risk=ProposalRisk(_string(root["risk"], field="risk")),
            test_adapter=_string(root["test_adapter"], field="test_adapter"),
            test_adapter_version=_string(
                root["test_adapter_version"],
                field="test_adapter_version",
            ),
            generation=generation,
        )
    except ProposalSchemaError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ProposalSchemaError("test proposal output failed strict validation") from error
