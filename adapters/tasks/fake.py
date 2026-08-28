"""Deterministic, network-free task publisher."""

from __future__ import annotations

from packages.domain import TaskMessage, TaskPublisherError


class FakeTaskPublisher:
    def __init__(self, *, failures_before_success: int = 0) -> None:
        if failures_before_success < 0:
            raise ValueError("failures_before_success cannot be negative")
        self._failures_remaining = failures_before_success
        self.messages: list[TaskMessage] = []

    def publish(self, message: TaskMessage) -> None:
        if self._failures_remaining:
            self._failures_remaining -= 1
            raise TaskPublisherError("planned fake broker outage")
        self.messages.append(message)
