"""Framework-light durable-task publication contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class TaskPublisherError(RuntimeError):
    """A safe publication error that may be retried through the durable outbox."""


@dataclass(frozen=True, slots=True)
class TaskMessage:
    topic: str
    payload: dict[str, str]
    idempotency_key: str

    def __post_init__(self) -> None:
        if self.topic != "releaseproof.analysis.process_job.v1":
            raise ValueError("task topic is not allowlisted")
        if set(self.payload) != {"organization_id", "job_id"}:
            raise ValueError("task payload may contain only opaque organization and job IDs")
        if not self.idempotency_key or len(self.idempotency_key) > 255:
            raise ValueError("task idempotency key is invalid")


class TaskPublisher(Protocol):
    def publish(self, message: TaskMessage) -> None: ...
