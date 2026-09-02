"""Bounded probe helpers used only by M9 sandbox sentinel tests."""

from __future__ import annotations

import sys
import time


def wait_forever() -> None:
    """Sleep until the outer sandbox wall-time controller terminates the container."""

    while True:
        time.sleep(1)


def emit_output(size: int = 100_000) -> None:
    """Emit deterministic text to prove output capture is bounded."""

    if sys.__stdout__ is None:
        raise RuntimeError("fixture stdout is unavailable")
    sys.__stdout__.write("releaseproof-output-sentinel-" * size)
    sys.__stdout__.flush()
