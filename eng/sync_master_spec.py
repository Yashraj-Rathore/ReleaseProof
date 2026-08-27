#!/usr/bin/env python3
"""Generate/check CODEX_MASTER_IMPLEMENTATION_SPEC.md from source-of-truth docs.

The master spec is a convenience artifact for single-file agent upload.
Edit source files instead, then rerun this script.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "CODEX_MASTER_IMPLEMENTATION_SPEC.md"

ROOT_SOURCES = [
    "README.md",
    "AGENTS.md",
    "CODEX_START_HERE.md",
    "CODEX_PROMPT_SEQUENCE.md",
    "IMPLEMENTATION_CHECKLIST.md",
    "PROJECT_STATUS.md",
    "CHANGELOG.md",
    "PACKAGE_MANIFEST.md",
]


def source_files() -> list[Path]:
    files = [ROOT / name for name in ROOT_SOURCES]
    files += sorted((ROOT / "docs").glob("[0-9][0-9]_*.md"))
    files += sorted((ROOT / "docs" / "decisions").glob("ADR-*.md"))
    files += sorted((ROOT / "templates").glob("*.md"))
    files += sorted((ROOT / "codex-prompts").glob("*.md"))
    return files


def render() -> str:
    parts = [
        "# ReleaseProof — Codex Master Implementation Specification\n\n"
        "> **GENERATED FILE — DO NOT EDIT DIRECTLY.**\n"
        "> Source-of-truth files are concatenated by `eng/sync_master_spec.py`.\n\n"
        "This single file exists for agent workflows that can accept only one specification file.\n"
    ]
    for path in source_files():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8").rstrip()
        parts.append(f"\n\n---\n\n# SOURCE FILE: `{rel}`\n\n{text}\n")
    return "".join(parts).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if generated output differs")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not OUTPUT.exists():
            print(f"missing: {OUTPUT.relative_to(ROOT)}")
            return 1
        actual = OUTPUT.read_text(encoding="utf-8")
        if actual != expected:
            print("CODEX_MASTER_IMPLEMENTATION_SPEC.md is out of date")
            return 1
        print("master spec is synchronized")
        return 0
    OUTPUT.write_text(expected, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({len(expected):,} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
