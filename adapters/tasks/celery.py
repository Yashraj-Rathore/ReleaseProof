"""Celery transport adapter; PostgreSQL outbox rows remain authoritative."""

from __future__ import annotations

from celery import current_app
from kombu.exceptions import KombuError

from packages.domain import TaskMessage, TaskPublisherError


class CeleryTaskPublisher:
    def publish(self, message: TaskMessage) -> None:
        try:
            current_app.send_task(
                message.topic,
                kwargs=message.payload,
                task_id=message.idempotency_key,
                ignore_result=True,
            )
        except (KombuError, OSError) as error:
            raise TaskPublisherError("task broker is unavailable") from error
