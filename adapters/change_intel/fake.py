"""Bounded, network-free inert source-tree provider."""

from __future__ import annotations

from collections.abc import Iterable

from packages.change_intel import SourceTree, SourceTreeProviderError


class FakeSourceTreeProvider:
    def __init__(
        self,
        trees: Iterable[SourceTree],
        *,
        failure: SourceTreeProviderError | None = None,
    ) -> None:
        self._trees: dict[tuple[str, str], SourceTree] = {}
        for tree in trees:
            key = (tree.repository_key, tree.revision)
            if key in self._trees:
                raise ValueError("fake source trees must have unique repository/revision keys")
            self._trees[key] = tree
        self._failure = failure
        self.requests: list[tuple[str, str]] = []

    def get_tree(self, *, repository_key: str, revision: str) -> SourceTree:
        self.requests.append((repository_key, revision))
        if self._failure is not None:
            raise self._failure
        try:
            return self._trees[(repository_key, revision)]
        except KeyError as error:
            raise SourceTreeProviderError(
                "source tree is not configured in the fake provider"
            ) from error
