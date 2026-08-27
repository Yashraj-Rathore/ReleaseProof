from __future__ import annotations

import pytest

from adapters.github import FakeGitHubProvider
from adapters.llm import FakeLLMProvider
from packages.ai_core import LLMRequest, LLMSchemaError, LLMSuggestion, LLMUnavailableError
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
        base_sha="a" * 40,
        head_sha="b" * 40,
        changed_files=(ChangedFile("src/fixture_app/pricing.py", 2, 1),),
    )


def test_github_fake_returns_exact_configured_snapshot() -> None:
    expected = _snapshot()
    provider = FakeGitHubProvider([expected])

    assert provider.get_pull_request(expected.repository, expected.number) == expected


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


def test_llm_fake_is_deterministic_and_rejects_unknown_citations() -> None:
    request = LLMRequest(change_id="change:7", evidence_ids=("evidence:7",))
    expected = LLMSuggestion(
        summary="Fixture-only response.",
        risk_hypotheses=("Rounding could change.",),
        requested_tests=("Check a boundary value.",),
        cited_evidence_ids=("evidence:7",),
    )
    provider = FakeLLMProvider(expected)

    assert provider.suggest(request) == expected
    assert provider.suggest(request) == expected

    invalid = FakeLLMProvider(
        LLMSuggestion(
            summary="Invalid citation fixture.",
            risk_hypotheses=(),
            requested_tests=(),
            cited_evidence_ids=("evidence:outside",),
        )
    )
    with pytest.raises(LLMSchemaError):
        invalid.suggest(request)


def test_llm_fake_has_explicit_unavailable_error() -> None:
    suggestion = LLMSuggestion("Unavailable", (), (), ())
    provider = FakeLLMProvider(suggestion, failure=LLMUnavailableError("planned outage"))

    with pytest.raises(LLMUnavailableError):
        provider.suggest(LLMRequest("change:1", ()))
