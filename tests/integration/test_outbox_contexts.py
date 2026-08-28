from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction

from adapters.tasks import FakeTaskPublisher
from apps.web.analysis.models import JobType, OutboxEvent, OutboxState
from apps.web.analysis.services import (
    create_job_with_outbox,
    process_ingestion_job,
    relay_outbox_for_organization,
)
from tests.factories import organization

pytestmark = pytest.mark.django_db


def _job(tenant, key: str):  # type: ignore[no-untyped-def]
    with transaction.atomic():
        return create_job_with_outbox(
            organization=tenant,
            job_type=JobType.INSTALLATION_LIFECYCLE,
            idempotency_key=key,
            correlation_id=uuid.uuid4(),
        )[0]


def test_management_relay_requires_explicit_tenant_and_never_crosses_scope() -> None:
    tenant_a = organization(name="Relay A", slug="relay-a")
    tenant_b = organization(name="Relay B", slug="relay-b")
    job_a = _job(tenant_a, "relay-a-job")
    job_b = _job(tenant_b, "relay-b-job")
    publisher = FakeTaskPublisher()

    with patch(
        "apps.web.analysis.management.commands.relay_outbox.CeleryTaskPublisher",
        return_value=publisher,
    ):
        call_command("relay_outbox", organization=str(tenant_a.public_id), limit=10)

    assert OutboxEvent.objects.get(job=job_a).state == OutboxState.PUBLISHED
    assert OutboxEvent.objects.get(job=job_b).state == OutboxState.PENDING
    assert publisher.messages[0].payload["organization_id"] == str(tenant_a.public_id)
    assert (
        process_ingestion_job(
            organization_public_id=str(tenant_b.public_id),
            job_public_id=str(job_a.public_id),
        )
        == "not_found"
    )


def test_management_relay_rejects_missing_tenant_context() -> None:
    with pytest.raises(CommandError, match="active organization not found"):
        call_command("relay_outbox", organization=str(uuid.uuid4()))


def test_outbox_publication_attempts_are_bounded_and_terminal() -> None:
    tenant = organization(name="Relay Bounded", slug="relay-bounded")
    job = _job(tenant, "relay-bounded-job")
    event = OutboxEvent.objects.get(job=job)
    event.max_attempts = 1
    event.save(update_fields=("max_attempts", "updated_at"))
    publisher = FakeTaskPublisher(failures_before_success=10)

    first = relay_outbox_for_organization(organization=tenant, publisher=publisher)
    event.refresh_from_db()
    assert first.failed == 1
    assert event.state == OutboxState.FAILED
    assert event.attempt_count == 1

    second = relay_outbox_for_organization(organization=tenant, publisher=publisher)
    event.refresh_from_db()
    assert second.published == 0
    assert second.failed == 0
    assert event.attempt_count == 1
