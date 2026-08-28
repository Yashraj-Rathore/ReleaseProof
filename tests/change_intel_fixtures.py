"""Inert synthetic source-tree fixtures for deterministic change-intelligence tests."""

from __future__ import annotations

from pathlib import Path

from packages.change_intel import SourceFile, SourceTree

ROOT = Path(__file__).resolve().parent
FIXTURE_ROOT = ROOT / "fixtures" / "repositories" / "releaseproof_fixture"
BASE_SHA = "a" * 40


def fixture_source_tree() -> SourceTree:
    paths = sorted(
        (
            *(FIXTURE_ROOT / "src").rglob("*.py"),
            *(FIXTURE_ROOT / "tests").rglob("*.py"),
            *(FIXTURE_ROOT / "frontend").rglob("*.js"),
        )
    )
    return SourceTree(
        repository_key="owner-2001/releaseproof",
        revision=BASE_SHA,
        files=tuple(
            SourceFile(
                path=path.relative_to(FIXTURE_ROOT).as_posix(),
                content=path.read_text(encoding="utf-8"),
            )
            for path in paths
        ),
    )
