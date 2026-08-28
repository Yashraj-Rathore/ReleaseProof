"""Stable changed-file normalization and language/file-type classification."""

from __future__ import annotations

from pathlib import PurePosixPath

from packages.change_intel.contracts import (
    DIFF_SCHEMA_VERSION,
    NormalizedDiff,
    NormalizedFile,
    RawChangedFile,
    canonical_hash,
)

MAX_CHANGED_FILES = 1_000
MAX_PATCH_BYTES = 65_536
MAX_TOTAL_PATCH_BYTES = 1_048_576
_ALLOWED_STATUSES = {"added", "modified", "removed", "renamed", "copied", "changed"}
_LANGUAGES = {
    ".css": "css",
    ".html": "html",
    ".js": "javascript",
    ".json": "json",
    ".jsx": "javascript",
    ".md": "markdown",
    ".py": "python",
    ".sh": "shell",
    ".sql": "sql",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".yaml": "yaml",
    ".yml": "yaml",
}
_BINARY_SUFFIXES = {
    ".7z",
    ".bin",
    ".class",
    ".dll",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".tar",
    ".webp",
    ".zip",
}
_DEPENDENCY_FILES = {
    "package-lock.json",
    "package.json",
    "poetry.lock",
    "pyproject.toml",
    "requirements.txt",
    "uv.lock",
}


def _path(value: str) -> str:
    normalized = value.replace("\\", "/").strip("/")
    if not normalized or len(normalized.encode("utf-8")) > 1_024:
        raise ValueError("changed path must be a bounded repository-relative path")
    parts = PurePosixPath(normalized).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("changed path contains an unsafe segment")
    return "/".join(parts)


def _truncate_utf8(value: str, maximum: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= maximum:
        return value.replace("\r\n", "\n"), False
    shortened = encoded[:maximum]
    while shortened:
        try:
            return shortened.decode("utf-8").replace("\r\n", "\n"), True
        except UnicodeDecodeError:
            shortened = shortened[:-1]
    return "", True


def _classify(path: str) -> tuple[str, str, bool, bool, bool, tuple[str, ...]]:
    pure = PurePosixPath(path)
    name = pure.name.casefold()
    parts = tuple(part.casefold() for part in pure.parts)
    suffix = pure.suffix.casefold()
    is_binary = suffix in _BINARY_SUFFIXES
    is_generated = any(part in {"dist", "generated", "build"} for part in parts)
    is_vendored = any(
        part in {"vendor", "vendored", "node_modules", "third_party"} for part in parts
    )
    language = "binary" if is_binary else _LANGUAGES.get(suffix, "unknown")
    if name in {"dockerfile", "containerfile"}:
        language = "dockerfile"
    if is_binary:
        file_type = "binary"
    elif is_generated:
        file_type = "generated"
    elif is_vendored:
        file_type = "vendored"
    elif name in _DEPENDENCY_FILES or name.endswith(".lock"):
        file_type = "dependency"
    elif "migrations" in parts and suffix in {".py", ".sql"}:
        file_type = "migration"
    elif any(part in {"test", "tests"} for part in parts) or name.startswith("test_"):
        file_type = "test"
    elif suffix in {".md", ".rst", ".txt"} and "requirements" not in name:
        file_type = "documentation"
    elif suffix in {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg"}:
        file_type = "configuration"
    elif language not in {"unknown", "binary"}:
        file_type = "source"
    else:
        file_type = "other"

    tags: set[str] = set()
    joined = "/".join(parts)
    if any(token in joined for token in ("auth", "identity", "permission", "security")):
        tags.add("auth_security")
    if file_type == "migration" or any(token in joined for token in ("schema", "database")):
        tags.add("database_schema")
    if any(part in {".github", "deploy", "infra", "terraform", "k8s"} for part in parts):
        tags.add("deployment_ci")
    if file_type == "dependency":
        tags.add("dependency_supply_chain")
    if any(token in joined for token in ("api", "urls", "routes")):
        tags.add("api_surface")
    return language, file_type, is_binary, is_generated, is_vendored, tuple(sorted(tags))


def normalize_diff(changed_files: tuple[RawChangedFile, ...]) -> NormalizedDiff:
    if len(changed_files) > MAX_CHANGED_FILES:
        raise ValueError("changed-file count exceeds the deterministic limit")
    normalized: list[NormalizedFile] = []
    consumed_patch_bytes = 0
    patch_set_truncated = False
    seen: set[str] = set()
    for item in sorted(changed_files, key=lambda file: file.path.replace("\\", "/")):
        path = _path(item.path)
        if path in seen:
            raise ValueError("changed-file paths must be unique")
        seen.add(path)
        if item.status not in _ALLOWED_STATUSES:
            raise ValueError("changed-file status is unsupported")
        if item.additions < 0 or item.deletions < 0:
            raise ValueError("line counts cannot be negative")
        previous_path = _path(item.previous_path) if item.previous_path else None
        if item.status == "renamed" and previous_path is None:
            raise ValueError("renamed files require previous_path")
        language, file_type, is_binary, is_generated, is_vendored, tags = _classify(path)
        patch: str | None = None
        patch_truncated = False
        if item.patch is not None and not is_binary:
            remaining = max(0, MAX_TOTAL_PATCH_BYTES - consumed_patch_bytes)
            patch, patch_truncated = _truncate_utf8(item.patch, min(MAX_PATCH_BYTES, remaining))
            consumed_patch_bytes += len(patch.encode("utf-8"))
            if remaining == 0 or patch_truncated:
                patch_set_truncated = True
        normalized.append(
            NormalizedFile(
                path=path,
                previous_path=previous_path,
                additions=item.additions,
                deletions=item.deletions,
                status=item.status,
                language=language,
                file_type=file_type,
                patch=patch,
                patch_truncated=patch_truncated,
                is_binary=is_binary,
                is_generated=is_generated,
                is_vendored=is_vendored,
                sensitive_tags=tags,
            )
        )
    payload = {
        "files": [file.as_dict() for file in normalized],
        "patch_set_truncated": patch_set_truncated,
        "schema_version": DIFF_SCHEMA_VERSION,
        "total_patch_bytes": consumed_patch_bytes,
    }
    return NormalizedDiff(
        schema_version=DIFF_SCHEMA_VERSION,
        files=tuple(normalized),
        total_patch_bytes=consumed_patch_bytes,
        patch_set_truncated=patch_set_truncated,
        diff_hash=canonical_hash(payload),
    )
