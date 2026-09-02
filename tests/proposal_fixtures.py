"""Deterministic M8 proposal fixtures shared by tests and evaluation."""

from __future__ import annotations

from adapters.test_generation.python_fixture import (
    PYTHON_FIXTURE_ADAPTER,
    PYTHON_FIXTURE_ADAPTER_VERSION,
    PythonFixtureTestAdapter,
    build_new_test_patch,
)
from packages.ai_core import (
    GeneratedTestProposalV1,
    ProposalGenerationMetadata,
    ProposalRisk,
)

VALID_TEST_PATH = "tests/generated/test_pricing_rounding.py"
VALID_TEST_CONTENT = (
    "from fixture_app.pricing import calculate_total\n"
    "\n"
    "\n"
    "def test_pricing_rounds_once() -> None:\n"
    "    assert calculate_total(100, 5) == 105\n"
)


def proposal_fixture(
    *,
    source_evidence_id: str = "evidence:00000000-0000-0000-0000-000000000001",
    evidence_ids: tuple[str, ...] = ("evidence:fixture:pricing",),
    file_path: str = VALID_TEST_PATH,
    patch: str | None = None,
    commands: tuple[str, ...] | None = None,
    target_behavior: str = "Pricing applies the percentage adjustment exactly once.",
    rationale: str = "The cited pricing evidence identifies a rounding regression risk.",
    expected_result: str = "The focused pricing regression test passes.",
    risk: ProposalRisk = ProposalRisk.MEDIUM,
    provider_name: str = "deterministic_fake",
    model_id: str = "deterministic-evidence-synthesizer-v1",
    provider_adapter_version: str = "deterministic-llm-fake-v1",
    prompt_version: str = "change-analysis-prompt-v1",
    prompt_sha256: str = "a" * 64,
) -> GeneratedTestProposalV1:
    resolved_patch = patch or build_new_test_patch(
        file_path=file_path,
        content=VALID_TEST_CONTENT,
    )
    resolved_commands = commands or (f"python -m pytest -q {file_path}",)
    generation = ProposalGenerationMetadata(
        provider_name=provider_name,
        model_id=model_id,
        provider_adapter_version=provider_adapter_version,
        prompt_version=prompt_version,
        prompt_sha256=prompt_sha256,
        source_evidence_id=source_evidence_id,
    )
    if patch is None and commands is None:
        return PythonFixtureTestAdapter().build_proposal(
            target_behavior=target_behavior,
            rationale=rationale,
            evidence_ids=evidence_ids,
            file_path=file_path,
            test_content=VALID_TEST_CONTENT,
            expected_result=expected_result,
            risk=risk,
            generation=generation,
        )
    return GeneratedTestProposalV1(
        target_behavior=target_behavior,
        rationale=rationale,
        evidence_ids=evidence_ids,
        file_path=file_path,
        patch=resolved_patch,
        commands=resolved_commands,
        expected_result=expected_result,
        risk=risk,
        test_adapter=PYTHON_FIXTURE_ADAPTER,
        test_adapter_version=PYTHON_FIXTURE_ADAPTER_VERSION,
        generation=generation,
    )
