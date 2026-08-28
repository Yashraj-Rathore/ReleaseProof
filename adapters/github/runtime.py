"""Fail-closed runtime provider selection for M2.

Tests patch this boundary with the deterministic fake. A live GitHub REST adapter is deliberately
not inferred without its own pinned authentication/HTTP implementation decision.
"""

from packages.github_contracts import (
    GitHubProvider,
    GitHubUnavailableError,
    PullRequestSnapshot,
)


class UnconfiguredGitHubProvider:
    def get_pull_request(
        self,
        repository: str,
        number: int,
        *,
        installation_id: int | None = None,
    ) -> PullRequestSnapshot:
        del repository, number, installation_id
        raise GitHubUnavailableError("GitHub pull-request provider is not configured")


def get_github_provider() -> GitHubProvider:
    return UnconfiguredGitHubProvider()
