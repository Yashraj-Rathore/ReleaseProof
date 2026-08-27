"""Small M1 GitHub contract used by the deterministic adapter.

Webhook verification, installation authentication, and persisted snapshots belong to M2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")


class GitHubProviderError(RuntimeError):
    """Base error safe for the core boundary."""


class GitHubNotFoundError(GitHubProviderError):
    """The configured repository or pull request does not exist."""


class GitHubUnavailableError(GitHubProviderError):
    """The provider could not serve a request."""


def _validate_text(value: str, *, field: str, maximum: int) -> None:
    if not value or len(value) > maximum or any(ord(character) < 32 for character in value):
        raise ValueError(f"{field} must contain 1..{maximum} printable characters")


@dataclass(frozen=True, slots=True)
class ChangedFile:
    path: str
    additions: int
    deletions: int

    def __post_init__(self) -> None:
        _validate_text(self.path, field="path", maximum=1024)
        if self.path.startswith(("/", "\\")) or ".." in self.path.replace("\\", "/").split("/"):
            raise ValueError("path must be repository-relative without parent traversal")
        if self.additions < 0 or self.deletions < 0:
            raise ValueError("line counts cannot be negative")


@dataclass(frozen=True, slots=True)
class PullRequestSnapshot:
    repository: str
    number: int
    title: str
    base_sha: str
    head_sha: str
    changed_files: tuple[ChangedFile, ...]

    def __post_init__(self) -> None:
        if not _REPOSITORY_PATTERN.fullmatch(self.repository):
            raise ValueError("repository must be an owner/name pair")
        if self.number < 1:
            raise ValueError("pull request number must be positive")
        _validate_text(self.title, field="title", maximum=256)
        if not _SHA_PATTERN.fullmatch(self.base_sha) or not _SHA_PATTERN.fullmatch(self.head_sha):
            raise ValueError("commit identifiers must be lowercase hexadecimal SHAs")
        if len(self.changed_files) > 1_000:
            raise ValueError("changed file count exceeds the M1 contract limit")


class GitHubProvider(Protocol):
    def get_pull_request(self, repository: str, number: int) -> PullRequestSnapshot: ...
