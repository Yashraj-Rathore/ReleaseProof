"""Provider-neutral, bounded GitHub contracts.

Provider SDK objects and installation credentials must not cross this boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_REF_PATTERN = re.compile(r"^[A-Za-z0-9_./-]{1,255}$")
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")
_CHECK_NAME_PATTERN = re.compile(r"^[^\x00-\x1f\x7f]{1,128}$")
MAX_CHANGED_FILES = 1_000
MAX_PATCH_BYTES = 65_536
MAX_TOTAL_PATCH_BYTES = 1_048_576


class GitHubProviderError(RuntimeError):
    """Base provider error with a message safe for the core boundary."""


class GitHubNotFoundError(GitHubProviderError):
    """The configured repository or pull request does not exist."""


class GitHubUnavailableError(GitHubProviderError):
    """The provider could not serve a request."""


class GitHubSchemaError(GitHubProviderError):
    """The provider returned data outside the bounded contract."""


def _validate_single_line(value: str, *, field: str, maximum: int) -> None:
    if not value or len(value) > maximum or any(ord(character) < 32 for character in value):
        raise ValueError(f"{field} must contain 1..{maximum} printable characters")


def _validate_bounded_text(value: str, *, field: str, maximum_bytes: int) -> None:
    if "\x00" in value or len(value.encode("utf-8")) > maximum_bytes:
        raise ValueError(f"{field} exceeds its bounded UTF-8 contract")


@dataclass(frozen=True, slots=True)
class ChangedFile:
    path: str
    additions: int
    deletions: int
    status: str = "modified"
    previous_path: str | None = None
    patch: str | None = None

    def __post_init__(self) -> None:
        _validate_single_line(self.path, field="path", maximum=1024)
        if self.path.startswith(("/", "\\")) or ".." in self.path.replace("\\", "/").split("/"):
            raise ValueError("path must be repository-relative without parent traversal")
        if self.additions < 0 or self.deletions < 0:
            raise ValueError("line counts cannot be negative")
        if self.status not in {"added", "modified", "removed", "renamed", "copied", "changed"}:
            raise ValueError("changed-file status is not supported")
        if self.previous_path is not None:
            _validate_single_line(self.previous_path, field="previous_path", maximum=1024)
        if self.patch is not None:
            _validate_bounded_text(self.patch, field="patch", maximum_bytes=MAX_PATCH_BYTES)


@dataclass(frozen=True, slots=True)
class CheckRun:
    name: str
    status: str
    conclusion: str | None = None

    def __post_init__(self) -> None:
        if not _CHECK_NAME_PATTERN.fullmatch(self.name):
            raise ValueError("check name must be a bounded printable string")
        if self.status not in {"queued", "in_progress", "completed", "unknown"}:
            raise ValueError("check status is not supported")
        if self.conclusion not in {
            None,
            "success",
            "failure",
            "neutral",
            "cancelled",
            "skipped",
            "timed_out",
            "action_required",
            "stale",
            "unknown",
        }:
            raise ValueError("check conclusion is not supported")


@dataclass(frozen=True, slots=True)
class PullRequestSnapshot:
    repository: str
    number: int
    title: str
    base_sha: str
    head_sha: str
    changed_files: tuple[ChangedFile, ...]
    repository_id: int | None = None
    body: str = ""
    base_ref: str = "unknown"
    head_ref: str = "unknown"
    checks: tuple[CheckRun, ...] = ()

    def __post_init__(self) -> None:
        if not _REPOSITORY_PATTERN.fullmatch(self.repository):
            raise ValueError("repository must be an owner/name pair")
        if self.repository_id is not None and self.repository_id < 1:
            raise ValueError("repository_id must be positive when present")
        if self.number < 1:
            raise ValueError("pull request number must be positive")
        _validate_single_line(self.title, field="title", maximum=256)
        _validate_bounded_text(self.body, field="body", maximum_bytes=65_536)
        if not _SHA_PATTERN.fullmatch(self.base_sha) or not _SHA_PATTERN.fullmatch(self.head_sha):
            raise ValueError("commit identifiers must be lowercase hexadecimal SHAs")
        if not _REF_PATTERN.fullmatch(self.base_ref) or not _REF_PATTERN.fullmatch(self.head_ref):
            raise ValueError("refs must be bounded Git reference names")
        if len(self.changed_files) > MAX_CHANGED_FILES:
            raise ValueError("changed file count exceeds the contract limit")
        patch_bytes = sum(
            len(changed_file.patch.encode("utf-8"))
            for changed_file in self.changed_files
            if changed_file.patch is not None
        )
        if patch_bytes > MAX_TOTAL_PATCH_BYTES:
            raise ValueError("combined patch content exceeds the contract limit")
        if len(self.checks) > 250:
            raise ValueError("check metadata exceeds the contract limit")


class AdvisoryConclusion(StrEnum):
    NEUTRAL = "neutral"
    ACTION_REQUIRED = "action_required"


@dataclass(frozen=True, slots=True)
class AdvisoryReport:
    repository_id: int
    pull_request_number: int
    head_sha: str
    name: str
    conclusion: AdvisoryConclusion
    summary: str
    details_url: str
    producer_version: str

    def __post_init__(self) -> None:
        if self.repository_id < 1 or self.pull_request_number < 1:
            raise ValueError("repository and pull-request identifiers must be positive")
        if not _SHA_PATTERN.fullmatch(self.head_sha):
            raise ValueError("head_sha must be a lowercase hexadecimal SHA")
        _validate_single_line(self.name, field="name", maximum=128)
        _validate_bounded_text(self.summary, field="summary", maximum_bytes=4_096)
        _validate_single_line(self.details_url, field="details_url", maximum=2_048)
        _validate_single_line(self.producer_version, field="producer_version", maximum=64)


@dataclass(frozen=True, slots=True)
class PublishedAdvisory:
    external_id: str
    report: AdvisoryReport


class GitHubProvider(Protocol):
    def get_pull_request(
        self,
        repository: str,
        number: int,
        *,
        installation_id: int | None = None,
    ) -> PullRequestSnapshot: ...


class GitHubAdvisoryPublisher(Protocol):
    def publish(self, report: AdvisoryReport) -> PublishedAdvisory: ...
