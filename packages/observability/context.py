"""Server-owned correlation context with optional OpenTelemetry trace lookup."""

from __future__ import annotations

import contextlib
import contextvars
import uuid
from collections.abc import Iterator

_CORRELATION_ID: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "releaseproof_correlation_id", default=None
)


def new_correlation_id() -> uuid.UUID:
    return uuid.uuid4()


def current_correlation_id() -> uuid.UUID:
    correlation_id = _CORRELATION_ID.get()
    return correlation_id if correlation_id is not None else new_correlation_id()


@contextlib.contextmanager
def correlation_scope(correlation_id: uuid.UUID | None = None) -> Iterator[uuid.UUID]:
    resolved = correlation_id or new_correlation_id()
    token = _CORRELATION_ID.set(resolved)
    try:
        yield resolved
    finally:
        _CORRELATION_ID.reset(token)


def current_trace_id() -> str | None:
    """Return the active trace ID without making OTel a core-package dependency."""

    try:
        from opentelemetry import trace
    except ImportError:
        return None
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    return f"{span_context.trace_id:032x}"
