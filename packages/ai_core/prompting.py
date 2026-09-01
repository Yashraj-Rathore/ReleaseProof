"""Versioned prompt loading and deterministic hostile-data serialization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from packages.ai_core.contracts import (
    EvidenceContext,
    LLMAnalysisRequest,
    LLMBudget,
    PromptIdentity,
)
from packages.ai_core.schema import ANALYSIS_SCHEMA_SHA256, ANALYSIS_SCHEMA_VERSION

PROMPT_VERSION = "change-analysis-prompt-v1"
_PROMPT_PATH = Path(__file__).with_name("prompts") / "change_analysis_v1.txt"
_PROMPT_BYTES = _PROMPT_PATH.read_bytes()
PROMPT_SHA256 = hashlib.sha256(_PROMPT_BYTES).hexdigest()
PROMPT_TEXT = _PROMPT_BYTES.decode("utf-8")
PROMPT_IDENTITY = PromptIdentity(
    prompt_version=PROMPT_VERSION,
    prompt_sha256=PROMPT_SHA256,
    schema_version=ANALYSIS_SCHEMA_VERSION,
    schema_sha256=ANALYSIS_SCHEMA_SHA256,
)


def build_analysis_request(
    *,
    change_id: str,
    evidence: tuple[EvidenceContext, ...],
    budget: LLMBudget,
    cancelled: bool = False,
) -> LLMAnalysisRequest:
    input_payload = {
        "change_id": change_id,
        "evidence": [
            {
                "content": item.content,
                "content_class": item.content_class.value,
                "evidence_id": item.evidence_id,
                "source_reference": item.source_reference,
            }
            for item in evidence
        ],
    }
    return LLMAnalysisRequest(
        change_id=change_id,
        evidence=evidence,
        instructions=PROMPT_TEXT,
        input_text=json.dumps(
            input_payload,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        prompt=PROMPT_IDENTITY,
        budget=budget,
        cancelled=cancelled,
    )
