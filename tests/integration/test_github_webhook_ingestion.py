from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse

from adapters.github import FakeGitHubProvider
from adapters.tasks import FakeTaskPublisher
from apps.web.analysis.models import AnalysisJob, JobState, OutboxEvent, OutboxState
from apps.web.analysis.services import process_ingestion_job, relay_outbox_for_organization
from apps.web.audit.models import AuditLog
from apps.web.changes.models import PullRequestSnapshot, WebhookReceipt
from apps.web.repositories.models import InstallationLifecycle, RepositoryLifecycle
from packages.github_contracts import ChangedFile, CheckRun
from packages.github_contracts import PullRequestSnapshot as ProviderSnapshot
from tests.factories import installation, organization, repository

pytestmark = pytest.mark.django_db


def _provider_snapshot(*, repository_id: int = 3001, head_sha: str = "b" * 40) -> ProviderSnapshot:
    return ProviderSnapshot(
        repository="owner-2001/releaseproof",
        repository_id=repository_id,
        number=7,
        title="Bounded fixture change",
        body="Synthetic fixture body.",
        base_ref="main",
        head_ref="feature/bounded",
        base_sha="a" * 40,
        head_sha=head_sha,
        changed_files=(
            ChangedFile(
                "src/fixture_app/pricing.py",
                2,
                1,
                patch="@@ -1 +1 @@\n-old\n+new",
            ),
        ),
        checks=(CheckRun("fixture-tests", "completed", "success"),),
    )


def _payload(*, installation_id: int = 1001, repository_id: int = 3001) -> bytes:
    return json.dumps(
        {
            "action": "opened",
            "installation": {"id": installation_id},
            "repository": {
                "id": repository_id,
                "full_name": "owner-2001/releaseproof",
            },
            "pull_request": {"number": 7},
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _headers(
    body: bytes,
    *,
    delivery: str = "delivery-0001",
    event: str = "pull_request",
) -> dict[str, str]:
    digest = hmac.new(settings.GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {
        "HTTP_X_HUB_SIGNATURE_256": f"sha256={digest}",
        "HTTP_X_GITHUB_DELIVERY": delivery,
        "HTTP_X_GITHUB_EVENT": event,
    }


def _bound_installation_and_repository():  # type: ignore[no-untyped-def]
    tenant = organization(name="Webhook Tenant", slug="webhook-tenant")
    github_installation = installation(
        organization=tenant,
        github_installation_id=1001,
        github_account_id=2001,
    )
    bound_repository = repository(
        organization=tenant,
        installation=github_installation,
        github_repository_id=3001,
        name="releaseproof",
    )
    return tenant, github_installation, bound_repository


def test_signed_pull_request_webhook_atomically_persists_snapshot_job_outbox_and_audit() -> None:
    tenant, _github_installation, _bound_repository = _bound_installation_and_repository()
    body = _payload()
    provider = FakeGitHubProvider([_provider_snapshot()])
    client = Client()

    with patch("apps.web.changes.views.get_github_provider", return_value=provider):
        response = client.post(
            reverse("github-webhook"),
            data=body,
            content_type="application/json",
            **_headers(body),
        )
    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert WebhookReceipt.objects.count() == 1
    snapshot = PullRequestSnapshot.objects.get()
    job = AnalysisJob.objects.get()
    outbox = OutboxEvent.objects.get()
    assert snapshot.organization == tenant
    assert snapshot.changed_files[0]["patch"].endswith("+new")
    assert snapshot.checks == [
        {"name": "fixture-tests", "status": "completed", "conclusion": "success"}
    ]
    assert len(snapshot.snapshot_checksum) == 64
    assert job.snapshot == snapshot
    assert job.state == JobState.PENDING
    assert outbox.state == OutboxState.PENDING
    assert set(outbox.payload) == {"organization_id", "job_id"}
    assert "token" not in json.dumps(outbox.payload).casefold()
    assert AuditLog.objects.filter(action="github.pull_request.accepted").count() == 1

    with patch("apps.web.changes.views.get_github_provider", return_value=provider):
        duplicate = client.post(
            reverse("github-webhook"),
            data=body,
            content_type="application/json",
            **_headers(body),
        )
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "deduplicated"
    assert WebhookReceipt.objects.count() == 1
    assert PullRequestSnapshot.objects.count() == 1
    assert AnalysisJob.objects.count() == 1
    assert OutboxEvent.objects.count() == 1


def test_tampered_unsupported_and_oversized_webhooks_fail_before_persistence() -> None:
    _bound_installation_and_repository()
    body = _payload()
    client = Client()

    tampered = client.post(
        reverse("github-webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256="sha256=" + "0" * 64,
        HTTP_X_GITHUB_DELIVERY="delivery-tampered",
        HTTP_X_GITHUB_EVENT="pull_request",
    )
    assert tampered.status_code == 401

    unsupported_body = body.replace(b'"opened"', b'"closed"')
    unsupported = client.post(
        reverse("github-webhook"),
        data=unsupported_body,
        content_type="application/json",
        **_headers(unsupported_body, delivery="delivery-unsupported"),
    )
    assert unsupported.status_code == 400

    oversized = client.post(
        reverse("github-webhook"),
        data=b"{}",
        content_type="application/json",
        HTTP_CONTENT_LENGTH=str(1_048_577),
        **_headers(b"{}", delivery="delivery-oversized"),
    )
    assert oversized.status_code == 413
    assert WebhookReceipt.objects.count() == 0


def test_delivery_id_reuse_with_different_signed_payload_is_rejected() -> None:
    _bound_installation_and_repository()
    provider = FakeGitHubProvider([_provider_snapshot()])
    first_body = _payload()
    second_body = first_body.replace(b'"number":7', b'"number":8')
    client = Client()

    with patch("apps.web.changes.views.get_github_provider", return_value=provider):
        first = client.post(
            reverse("github-webhook"),
            data=first_body,
            content_type="application/json",
            **_headers(first_body, delivery="delivery-reused"),
        )
        second = client.post(
            reverse("github-webhook"),
            data=second_body,
            content_type="application/json",
            **_headers(second_body, delivery="delivery-reused"),
        )
    assert first.status_code == 202
    assert second.status_code == 409
    assert WebhookReceipt.objects.count() == 1


def test_broker_failure_leaves_outbox_pending_and_recovery_and_worker_are_idempotent() -> None:
    tenant, _github_installation, _bound_repository = _bound_installation_and_repository()
    body = _payload()
    provider = FakeGitHubProvider([_provider_snapshot()])
    with patch("apps.web.changes.views.get_github_provider", return_value=provider):
        response = Client().post(
            reverse("github-webhook"),
            data=body,
            content_type="application/json",
            **_headers(body),
        )
    assert response.status_code == 202
    outbox = OutboxEvent.objects.get()
    publisher = FakeTaskPublisher(failures_before_success=1)

    failed = relay_outbox_for_organization(organization=tenant, publisher=publisher)
    outbox.refresh_from_db()
    assert failed.failed == 1
    assert outbox.state == OutboxState.PENDING
    assert outbox.last_error_code == "broker_unavailable"

    recovered = relay_outbox_for_organization(organization=tenant, publisher=publisher)
    outbox.refresh_from_db()
    assert recovered.published == 1
    assert outbox.state == OutboxState.PUBLISHED
    assert len(publisher.messages) == 1
    message = publisher.messages[0]
    assert set(message.payload) == {"organization_id", "job_id"}
    assert (
        process_ingestion_job(
            organization_public_id=message.payload["organization_id"],
            job_public_id=message.payload["job_id"],
        )
        == "completed"
    )
    assert (
        process_ingestion_job(
            organization_public_id=message.payload["organization_id"],
            job_public_id=message.payload["job_id"],
        )
        == "duplicate"
    )
    job = AnalysisJob.objects.get()
    assert job.state == JobState.COMPLETED
    assert job.attempt_count == 1


def test_snapshot_and_receipt_are_immutable_at_application_and_database_boundaries() -> None:
    _bound_installation_and_repository()
    body = _payload()
    provider = FakeGitHubProvider([_provider_snapshot()])
    with patch("apps.web.changes.views.get_github_provider", return_value=provider):
        assert (
            Client()
            .post(
                reverse("github-webhook"),
                data=body,
                content_type="application/json",
                **_headers(body),
            )
            .status_code
            == 202
        )
    snapshot = PullRequestSnapshot.objects.get()
    snapshot.title = "mutated"
    with pytest.raises(ValidationError, match="immutable"):
        snapshot.save()
    with pytest.raises(ValidationError, match="immutable"):
        PullRequestSnapshot.objects.filter(pk=snapshot.pk).update(title="mutated")
    with (
        pytest.raises(DatabaseError, match="immutable"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE changes_pullrequestsnapshot SET title = %s WHERE id = %s",
            ["raw mutation", snapshot.pk],
        )


def test_signed_installation_and_repository_lifecycle_events_are_tenant_bound() -> None:
    tenant, github_installation, _bound_repository = _bound_installation_and_repository()
    client = Client()
    suspend_body = json.dumps(
        {"action": "suspend", "installation": {"id": github_installation.github_installation_id}},
        separators=(",", ":"),
    ).encode()
    suspended = client.post(
        reverse("github-webhook"),
        data=suspend_body,
        content_type="application/json",
        **_headers(suspend_body, delivery="delivery-suspend", event="installation"),
    )
    assert suspended.status_code == 202
    github_installation.refresh_from_db()
    assert github_installation.lifecycle == InstallationLifecycle.SUSPENDED

    pull_body = _payload()
    provider = FakeGitHubProvider([_provider_snapshot()])
    with patch("apps.web.changes.views.get_github_provider", return_value=provider):
        rejected_pull = client.post(
            reverse("github-webhook"),
            data=pull_body,
            content_type="application/json",
            **_headers(pull_body, delivery="delivery-while-suspended"),
        )
    assert rejected_pull.status_code == 404

    unsuspend_body = suspend_body.replace(b'"suspend"', b'"unsuspend"')
    assert (
        client.post(
            reverse("github-webhook"),
            data=unsuspend_body,
            content_type="application/json",
            **_headers(unsuspend_body, delivery="delivery-unsuspend", event="installation"),
        ).status_code
        == 202
    )

    added_body = json.dumps(
        {
            "action": "added",
            "installation": {"id": github_installation.github_installation_id},
            "repositories_added": [
                {
                    "id": 3002,
                    "full_name": "owner-2001/new-repository",
                    "default_branch": "trunk",
                }
            ],
        },
        separators=(",", ":"),
    ).encode()
    assert (
        client.post(
            reverse("github-webhook"),
            data=added_body,
            content_type="application/json",
            **_headers(
                added_body, delivery="delivery-repo-added", event="installation_repositories"
            ),
        ).status_code
        == 202
    )
    bound = tenant.repositories.get(github_repository_id=3002)
    assert bound.default_branch == "trunk"
    assert bound.lifecycle == RepositoryLifecycle.ACTIVE

    removed_body = added_body.replace(b'"added"', b'"removed"').replace(
        b'"repositories_added"', b'"repositories_removed"'
    )
    assert (
        client.post(
            reverse("github-webhook"),
            data=removed_body,
            content_type="application/json",
            **_headers(
                removed_body,
                delivery="delivery-repo-removed",
                event="installation_repositories",
            ),
        ).status_code
        == 202
    )
    bound.refresh_from_db()
    assert bound.lifecycle == RepositoryLifecycle.REMOVED
