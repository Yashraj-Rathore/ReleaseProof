from __future__ import annotations

from dataclasses import replace

import pytest

from adapters.github import FakeGitHubProvider
from adapters.llm import FakeLLMProvider
from packages.ai_core import (
    ContentClass,
    EvidenceContext,
    LLMAnalysisRequest,
    LLMBudget,
    LLMSchemaError,
    LLMUnavailableError,
    build_analysis_request,
)
from packages.github_contracts import (
    ChangedFile,
    GitHubNotFoundError,
    GitHubUnavailableError,
    PullRequestSnapshot,
)


def _snapshot() -> PullRequestSnapshot:
    return PullRequestSnapshot(
        repository="releaseproof/fixture",
        number=7,
        title="Fixture change",
        author_key="fixture-author",
        commit_count=2,
        base_sha="a" * 40,
        head_sha="b" * 40,
        changed_files=(ChangedFile("src/fixture_app/pricing.py", 2, 1),),
    )


def test_github_fake_returns_exact_configured_snapshot() -> None:
    expected = _snapshot()
    provider = FakeGitHubProvider([expected])

    assert provider.get_pull_request(expected.repository, expected.number) == expected
    assert expected.author_key == "fixture-author"
    assert expected.commit_count == 2

    with pytest.raises(ValueError, match="author_key"):
        replace(expected, author_key="raw user name")


def test_github_fake_has_explicit_not_found_and_unavailable_errors() -> None:
    with pytest.raises(GitHubNotFoundError):
        FakeGitHubProvider([]).get_pull_request("releaseproof/missing", 1)

    provider = FakeGitHubProvider([], failure=GitHubUnavailableError("planned outage"))
    with pytest.raises(GitHubUnavailableError):
        provider.get_pull_request("releaseproof/fixture", 1)


def test_github_fake_rejects_ambiguous_duplicate_configuration() -> None:
    snapshot = _snapshot()

    with pytest.raises(ValueError, match="unique"):
        FakeGitHubProvider([snapshot, snapshot])


def _llm_request() -> LLMAnalysisRequest:
    return build_analysis_request(
        change_id="change:7",
        evidence=(
            EvidenceContext(
                evidence_id="evidence:7",
                content_class=ContentClass.DETERMINISTIC_EVIDENCE,
                content="A fixture behavior changed.",
                source_reference="fixture:evidence:7",
            ),
        ),
        budget=LLMBudget(
            max_input_bytes=16_384,
            max_input_tokens=16_384,
            max_output_tokens=1_024,
            max_cost_microusd=100_000,
            connect_timeout_seconds=5.0,
            read_timeout_seconds=30.0,
            max_attempts=2,
            retry_backoff_seconds=0.5,
        ),
    )


def test_llm_fake_is_deterministic_and_rejects_unknown_citations() -> None:
    request = _llm_request()
    provider = FakeLLMProvider()

    first = provider.analyze_change(request)
    second = provider.analyze_change(request)
    assert first.suggestion == second.suggestion
    assert first.usage.cost_microusd == 0

    invalid = FakeLLMProvider(
        raw_output=(
            '{"summary":"Invalid citation fixture.",'
            '"summary_evidence_ids":["evidence:outside"],"risks":[],"hypotheses":[],'
            '"requested_tests":[],"missing_information":[],"uncertainty":"Fixture.",'
            '"insufficient_evidence":false}'
        )
    )
    with pytest.raises(LLMSchemaError):
        invalid.analyze_change(request)


def test_llm_fake_has_explicit_unavailable_error() -> None:
    provider = FakeLLMProvider(failure=LLMUnavailableError("planned outage"))

    with pytest.raises(LLMUnavailableError):
        provider.analyze_change(_llm_request())
