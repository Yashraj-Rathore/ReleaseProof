#!/usr/bin/env python3
"""Generate or check the repository's deterministic source-file inventory."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "FILE_INVENTORY.md"
EXCLUDED_DIRECTORIES = {
    ".bootstrap-uv",
    ".git",
    ".mypy_cache",
    ".pre-commit-cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".uv-python",
    ".venv",
    "__pycache__",
    "artifacts",
    "local-data",
    "mlruns",
    "node_modules",
    "secrets",
}


def source_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path == OUTPUT:
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_DIRECTORIES for part in relative.parts):
            continue
        if relative.name == ".env" or relative.suffix in {".log", ".pem", ".key", ".crt"}:
            continue
        if relative.as_posix() == "deploy/seaweedfs/s3.local.json":
            continue
        files.append(path)
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def render() -> str:
    lines = [
        "# File Inventory",
        "",
        "This inventory excludes itself, Git metadata, environments, caches, secrets, logs, and",
        "runtime data so every listed hash is stable.",
        "",
        "| Path | Bytes | SHA-256 |",
        "|---|---:|---|",
    ]
    for path in source_files():
        content = path.read_bytes()
        relative = path.relative_to(ROOT).as_posix()
        digest = hashlib.sha256(content).hexdigest()
        lines.append(f"| `{relative}` | {len(content)} | `{digest}` |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the inventory differs")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != expected:
            print("FILE_INVENTORY.md is out of date")
            return 1
        print("file inventory is synchronized")
        return 0
    OUTPUT.write_text(expected, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({len(source_files())} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
