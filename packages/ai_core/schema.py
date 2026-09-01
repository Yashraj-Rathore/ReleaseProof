"""Strict source-controlled schema loading and provider-output validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, NoReturn, cast

from packages.ai_core.contracts import (
    AnalysisSuggestionV1,
    ConfidenceCategory,
    GroundedRisk,
    LLMSchemaError,
    RequestedTest,
    RiskHypothesis,
    Severity,
)

ANALYSIS_SCHEMA_VERSION = "analysis-suggestion-v1"
_SCHEMA_PATH = Path(__file__).with_name("schemas") / "analysis_suggestion_v1.json"
_SCHEMA_BYTES = _SCHEMA_PATH.read_bytes()
ANALYSIS_SCHEMA_SHA256 = hashlib.sha256(_SCHEMA_BYTES).hexdigest()
ANALYSIS_JSON_SCHEMA = cast(dict[str, Any], json.loads(_SCHEMA_BYTES))
MAX_PROVIDER_OUTPUT_BYTES = 64 * 1024

_ROOT_KEYS = {
    "summary",
    "summary_evidence_ids",
    "risks",
    "hypotheses",
    "requested_tests",
    "missing_information",
    "uncertainty",
    "insufficient_evidence",
}
_RISK_KEYS = {"statement", "severity", "confidence", "evidence_ids"}
_HYPOTHESIS_KEYS = _RISK_KEYS | {"uncertainty"}
_TEST_KEYS = {"description", "rationale", "evidence_ids"}


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
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or not all(isinstance(key, str) for key in value)
    ):
        raise LLMSchemaError(f"{field} has an invalid object shape")
    return cast(dict[str, object], value)


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise LLMSchemaError(f"{field} must be a string")
    return value


def _strings(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise LLMSchemaError(f"{field} must be a string array")
    return tuple(value)


def _items(value: object, *, field: str) -> list[object]:
    if not isinstance(value, list):
        raise LLMSchemaError(f"{field} must be an array")
    return value


def parse_suggestion_json(raw_output: str) -> AnalysisSuggestionV1:
    """Reject malformed/extra/coerced provider output and return a typed suggestion."""

    if not isinstance(raw_output, str) or not raw_output:
        raise LLMSchemaError("provider output must be non-empty text")
    if len(raw_output.encode()) > MAX_PROVIDER_OUTPUT_BYTES:
        raise LLMSchemaError("provider output exceeds the strict byte bound")
    try:
        decoded = json.loads(
            raw_output,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
        root = _object(decoded, keys=_ROOT_KEYS, field="root")
        risks = tuple(
            GroundedRisk(
                statement=_string(item["statement"], field="risk.statement"),
                severity=Severity(_string(item["severity"], field="risk.severity")),
                confidence=ConfidenceCategory(_string(item["confidence"], field="risk.confidence")),
                evidence_ids=_strings(item["evidence_ids"], field="risk.evidence_ids"),
            )
            for value in _items(root["risks"], field="risks")
            for item in (_object(value, keys=_RISK_KEYS, field="risk"),)
        )
        hypotheses = tuple(
            RiskHypothesis(
                statement=_string(item["statement"], field="hypothesis.statement"),
                severity=Severity(_string(item["severity"], field="hypothesis.severity")),
                confidence=ConfidenceCategory(
                    _string(item["confidence"], field="hypothesis.confidence")
                ),
                evidence_ids=_strings(item["evidence_ids"], field="hypothesis.evidence_ids"),
                uncertainty=_string(item["uncertainty"], field="hypothesis.uncertainty"),
            )
            for value in _items(root["hypotheses"], field="hypotheses")
            for item in (_object(value, keys=_HYPOTHESIS_KEYS, field="hypothesis"),)
        )
        requested_tests = tuple(
            RequestedTest(
                description=_string(item["description"], field="test.description"),
                rationale=_string(item["rationale"], field="test.rationale"),
                evidence_ids=_strings(item["evidence_ids"], field="test.evidence_ids"),
            )
            for value in _items(root["requested_tests"], field="requested_tests")
            for item in (_object(value, keys=_TEST_KEYS, field="requested_test"),)
        )
        insufficient = root["insufficient_evidence"]
        if not isinstance(insufficient, bool):
            raise LLMSchemaError("insufficient_evidence must be boolean")
        return AnalysisSuggestionV1(
            summary=_string(root["summary"], field="summary"),
            summary_evidence_ids=_strings(
                root["summary_evidence_ids"], field="summary_evidence_ids"
            ),
            risks=risks,
            hypotheses=hypotheses,
            requested_tests=requested_tests,
            missing_information=_strings(root["missing_information"], field="missing_information"),
            uncertainty=_string(root["uncertainty"], field="uncertainty"),
            insufficient_evidence=insufficient,
        )
    except LLMSchemaError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise LLMSchemaError("provider output failed strict schema validation") from error


def validate_suggestion_citations(
    suggestion: AnalysisSuggestionV1,
    *,
    allowed_evidence_ids: tuple[str, ...],
) -> None:
    allowed = set(allowed_evidence_ids)
    if not set(suggestion.cited_evidence_ids).issubset(allowed):
        raise LLMSchemaError("provider output cites evidence outside the request")
    if not allowed and not suggestion.insufficient_evidence:
        raise LLMSchemaError("provider output claims sufficient evidence without evidence")
