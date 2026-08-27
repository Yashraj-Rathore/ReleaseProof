"""Deterministic, network-free GitHub provider."""

from __future__ import annotations

from collections.abc import Iterable

from packages.github_contracts import (
    GitHubNotFoundError,
    GitHubProviderError,
    PullRequestSnapshot,
)


class FakeGitHubProvider:
    def __init__(
        self,
        snapshots: Iterable[PullRequestSnapshot],
        *,
        failure: GitHubProviderError | None = None,
    ) -> None:
        self._snapshots: dict[tuple[str, int], PullRequestSnapshot] = {}
        for snapshot in snapshots:
            key = (snapshot.repository, snapshot.number)
            if key in self._snapshots:
                raise ValueError("fake GitHub snapshots must have unique repository/number keys")
            self._snapshots[key] = snapshot
        self._failure = failure

    def get_pull_request(self, repository: str, number: int) -> PullRequestSnapshot:
        if self._failure is not None:
            raise self._failure
        try:
            return self._snapshots[(repository, number)]
        except KeyError as error:
            raise GitHubNotFoundError(
                "pull request is not configured in the fake provider"
            ) from error
