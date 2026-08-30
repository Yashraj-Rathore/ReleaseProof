#!/usr/bin/env python3
"""Cross-platform M1 validation orchestrator used locally and in CI."""

from __future__ import annotations

import subprocess
import sys

COMMANDS = (
    (sys.executable, "-m", "ruff", "format", "--check", "."),
    (sys.executable, "-m", "ruff", "check", "."),
    (sys.executable, "-m", "mypy"),
    (sys.executable, "-m", "pytest", "-m", "not integration"),
    (
        sys.executable,
        "manage.py",
        "check",
        "--settings=apps.web.releaseproof.settings.test",
    ),
    (
        sys.executable,
        "manage.py",
        "makemigrations",
        "--check",
        "--dry-run",
        "--settings=apps.web.releaseproof.settings.test",
    ),
    (sys.executable, "eng/sync_master_spec.py", "--check"),
    (sys.executable, "eng/update_file_inventory.py", "--check"),
    (sys.executable, "-m", "eng.evaluate_m4_baseline", "--check"),
)


def main() -> int:
    for command in COMMANDS:
        print(f"+ {' '.join(command)}", flush=True)
        completed = subprocess.run(command, check=False)  # noqa: S603
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
