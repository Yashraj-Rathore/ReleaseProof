from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.web.audit.models import AuditLog
from apps.web.changes.models import PullRequestSnapshot, WebhookReceipt
from apps.web.organizations.models import (
    MembershipRole,
    RetentionDeletionExecution,
    RetentionDeletionGrant,
    UsageCounter,
    UsageReservation,
)
from apps.web.organizations.operational_services import (
    OperationalPolicyError,
    QuotaExceededError,
    create_operational_policy,
    create_retention_deletion_plan,
    execute_retention_deletion_plan,
    reserve_quota,
    reserve_upload,
    validate_upload_size,
)
from packages.observability import DEFAULT_QUOTA_LIMITS, DEFAULT_RETENTION_DAYS, QuotaKind
from tests.factories import installation, membership, organization, repository, user

pytestmark = pytest.mark.django_db


def _owner_fixture() -> tuple[object, object, object, object]:
    tenant = organization(name="Operational tenant", slug=f"ops-{uuid.uuid4().hex[:8]}")
    owner = user(username=f"owner-{uuid.uuid4().hex[:8]}")
    outsider = user(username=f"outsider-{uuid.uuid4().hex[:8]}")
    membership(organization=tenant, user=owner, role=MembershipRole.OWNER)
    install = installation(
        organization=tenant,
        github_installation_id=10_000 + tenant.id,
        github_account_id=20_000 + tenant.id,
    )
    repo = repository(
        organization=tenant,
        installation=install,
        github_repository_id=30_000 + tenant.id,
        name="operational-fixture",
    )
    return tenant, owner, outsider, repo


def test_policy_and_quota_reservations_are_tenant_user_scoped_and_idempotent() -> None:
    tenant, owner, outsider, _repo = _owner_fixture()
    limits = dict(DEFAULT_QUOTA_LIMITS)
    limits[QuotaKind.RETRIEVAL_QUERIES_PER_MINUTE.value] = 2
    policy = create_operational_policy(
        organization=tenant,
        actor=owner,
        quota_limits=limits,
        retention_days=DEFAULT_RETENTION_DAYS,
    )

    first = reserve_quota(
        organization=tenant,
        actor=owner,
        kind=QuotaKind.RETRIEVAL_QUERIES_PER_MINUTE,
        quantity=2,
        idempotency_key="retrieval:fixed-operation",
    )
    duplicate = reserve_quota(
        organization=tenant,
        actor=owner,
        kind=QuotaKind.RETRIEVAL_QUERIES_PER_MINUTE,
        quantity=2,
        idempotency_key="retrieval:fixed-operation",
    )

    assert policy.version == 1
    assert len(first.reservations) == 2
    assert duplicate.duplicate is True
    assert UsageCounter.objects.filter(organization=tenant).count() == 2
    assert UsageReservation.objects.filter(organization=tenant).count() == 2
    with pytest.raises(QuotaExceededError):
        reserve_quota(
            organization=tenant,
            actor=owner,
            kind=QuotaKind.RETRIEVAL_QUERIES_PER_MINUTE,
            quantity=1,
            idempotency_key="retrieval:over-limit",
        )
    assert set(
        UsageCounter.objects.filter(organization=tenant).values_list("consumed", flat=True)
    ) == {2}
    with pytest.raises(OperationalPolicyError, match="owner_or_admin_required"):
        create_operational_policy(
            organization=tenant,
            actor=outsider,
            quota_limits=limits,
            retention_days=DEFAULT_RETENTION_DAYS,
        )


def test_upload_size_and_tenant_user_request_limits_are_independent() -> None:
    tenant, owner, _outsider, _repo = _owner_fixture()
    limit = DEFAULT_QUOTA_LIMITS[QuotaKind.UPLOAD_BYTES_PER_REQUEST.value]

    validate_upload_size(organization=tenant, byte_count=limit)
    with pytest.raises(QuotaExceededError):
        validate_upload_size(organization=tenant, byte_count=limit + 1)
    first = reserve_upload(
        organization=tenant,
        actor=owner,
        byte_count=limit,
        idempotency_key="upload:fixture",
    )
    duplicate = reserve_upload(
        organization=tenant,
        actor=owner,
        byte_count=limit,
        idempotency_key="upload:fixture",
    )
    assert len(first.reservations) == 2
    assert duplicate.duplicate is True
    assert set(
        UsageReservation.objects.filter(organization=tenant).values_list("scope", flat=True)
    ) == {"tenant", "user"}


def test_retention_dry_run_and_exact_execution_preserve_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, owner, _outsider, repo = _owner_fixture()
    install = repo.installation
    old_now = timezone.now() - timedelta(days=10)
    with monkeypatch.context() as context:
        context.setattr(timezone, "now", lambda: old_now)
        receipt = WebhookReceipt.objects.create(
            organization=tenant,
            installation=install,
            delivery_id=f"old-{uuid.uuid4().hex}",
            event_name="pull_request",
            action="opened",
            payload_sha256="a" * 64,
            payload_size=100,
        )
        snapshot = PullRequestSnapshot.objects.create(
            organization=tenant,
            repository=repo,
            first_receipt=receipt,
            pull_request_number=1,
            title="old synthetic snapshot",
            body="",
            base_ref="main",
            head_ref="feature",
            base_sha="a" * 40,
            head_sha="b" * 40,
            changed_files=[],
            checks=[],
            snapshot_checksum="c" * 64,
        )
    retention = dict(DEFAULT_RETENTION_DAYS)
    retention["source_snapshot"] = 1
    create_operational_policy(
        organization=tenant,
        actor=owner,
        quota_limits=DEFAULT_QUOTA_LIMITS,
        retention_days=retention,
    )

    dry_run = create_retention_deletion_plan(organization=tenant, actor=owner, dry_run=True)
    assert str(snapshot.public_id) in dry_run.candidate_public_ids["source_snapshot"]
    with pytest.raises(ValueError, match="dry_run"):
        execute_retention_deletion_plan(
            organization=tenant,
            plan_public_id=dry_run.public_id,
            actor=owner,
        )
    assert PullRequestSnapshot.objects.filter(pk=snapshot.pk).exists()

    execute_plan = create_retention_deletion_plan(organization=tenant, actor=owner, dry_run=False)
    result = execute_retention_deletion_plan(
        organization=tenant,
        plan_public_id=execute_plan.public_id,
        actor=owner,
    )

    assert result.execution.deleted_counts["source_snapshot"] == 1
    assert not PullRequestSnapshot.objects.filter(pk=snapshot.pk).exists()
    assert RetentionDeletionExecution.objects.filter(plan=execute_plan).exists()
    assert AuditLog.objects.filter(organization=tenant, action="retention.plan_executed").exists()


def test_immutable_snapshot_raw_delete_requires_exact_planned_candidate() -> None:
    tenant, owner, _outsider, repo = _owner_fixture()
    receipt = WebhookReceipt.objects.create(
        organization=tenant,
        installation=repo.installation,
        delivery_id=f"current-{uuid.uuid4().hex}",
        event_name="pull_request",
        action="opened",
        payload_sha256="d" * 64,
        payload_size=100,
    )
    snapshot = PullRequestSnapshot.objects.create(
        organization=tenant,
        repository=repo,
        first_receipt=receipt,
        pull_request_number=2,
        title="current snapshot",
        body="",
        base_ref="main",
        head_ref="feature",
        base_sha="d" * 40,
        head_sha="e" * 40,
        changed_files=[],
        checks=[],
        snapshot_checksum="f" * 64,
    )
    public_id = snapshot.public_id.hex if connection.vendor == "sqlite" else str(snapshot.public_id)

    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            'DELETE FROM "changes_pullrequestsnapshot" WHERE "organization_id" = %s '
            'AND "public_id" = %s',
            (tenant.pk, public_id),
        )
    assert PullRequestSnapshot.objects.filter(pk=snapshot.pk).exists()

    unrelated_plan = create_retention_deletion_plan(
        organization=tenant,
        actor=owner,
        dry_run=False,
    )
    assert str(snapshot.public_id) not in unrelated_plan.candidate_public_ids["source_snapshot"]
    grant = RetentionDeletionGrant.objects.create(
        organization=tenant,
        plan=unrelated_plan,
        active=True,
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            'DELETE FROM "changes_pullrequestsnapshot" WHERE "organization_id" = %s '
            'AND "public_id" = %s',
            (tenant.pk, public_id),
        )
    RetentionDeletionGrant.objects.filter(pk=grant.pk).update(active=False)
    assert PullRequestSnapshot.objects.filter(pk=snapshot.pk).exists()
