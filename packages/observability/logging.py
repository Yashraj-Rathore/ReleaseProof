"""Allowlisted JSON logs that never serialize arbitrary messages or exception text."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Final

_SAFE_EVENT_CHARS: Final = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)
_SAFE_OUTCOMES: Final = frozenset(
    {"accepted", "completed", "denied", "failed", "unknown", "unavailable"}
)


def _bounded_code(value: object, *, fallback: str, maximum: int = 96) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        return fallback
    if not value.isascii() or any(character not in _SAFE_EVENT_CHARS for character in value):
        return fallback
    return value


class SafeJsonFormatter(logging.Formatter):
    """Emit only server-owned bounded fields; raw ``record.msg`` is intentionally ignored."""

    def format(self, record: logging.LogRecord) -> str:
        from packages.observability.context import current_correlation_id, current_trace_id

        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": _bounded_code(record.name, fallback="application"),
            "event": _bounded_code(getattr(record, "event", None), fallback="log_event"),
            "correlation_id": str(current_correlation_id()),
        }
        trace_id = current_trace_id()
        if trace_id is not None:
            payload["trace_id"] = trace_id
        outcome = getattr(record, "outcome", None)
        if outcome in _SAFE_OUTCOMES:
            payload["outcome"] = outcome
        duration_ms = getattr(record, "duration_ms", None)
        if isinstance(duration_ms, (int, float)) and not isinstance(duration_ms, bool):
            payload["duration_ms"] = max(0.0, min(float(duration_ms), 86_400_000.0))
        if record.exc_info is not None and record.exc_info[0] is not None:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def safe_log(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    outcome: str | None = None,
    duration_ms: float | None = None,
    exc_info: bool = False,
) -> None:
    extra: dict[str, object] = {"event": _bounded_code(event, fallback="invalid_event")}
    if outcome is not None:
        extra["outcome"] = outcome
    if duration_ms is not None:
        extra["duration_ms"] = duration_ms
    logger.log(level, "releaseproof_event", extra=extra, exc_info=exc_info)
