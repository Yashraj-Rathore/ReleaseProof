from __future__ import annotations

import hashlib
import uuid

import pytest

from adapters.github import FakeGitHubAdvisoryPublisher
from apps.web.changes.models import PullRequestSnapshot, WebhookReceipt
from apps.web.verification.services import StaleSnapshotError, publish_snapshot_advisory
from packages.github_contracts import AdvisoryConclusion
from tests.factories import installation, organization, repository

pytestmark = pytest.mark.django_db


def _receipt(*, tenant, github_installation, delivery: str):  # type: ignore[no-untyped-def]
    receipt = WebhookReceipt(
        organization=tenant,
        installation=github_installation,
        delivery_id=delivery,
        event_name="pull_request",
        action="synchronize",
        payload_sha256=hashlib.sha256(delivery.encode()).hexdigest(),
        payload_size=len(delivery),
        correlation_id=uuid.uuid4(),
    )
    receipt.full_clean()
    receipt.save()
    return receipt


def _snapshot(*, tenant, bound_repository, receipt, head_sha: str, checksum_seed: str):  # type: ignore[no-untyped-def]
    snapshot = PullRequestSnapshot(
        organization=tenant,
        repository=bound_repository,
        first_receipt=receipt,
        pull_request_number=11,
        title="Advisory fixture",
        body="",
        base_ref="main",
        head_ref="feature/advisory",
        base_sha="a" * 40,
        head_sha=head_sha,
        changed_files=[],
        checks=[],
        snapshot_checksum=hashlib.sha256(checksum_seed.encode()).hexdigest(),
    )
    snapshot.full_clean()
    snapshot.save()
    return snapshot


def test_fake_advisory_publish_is_neutral_versioned_and_stale_safe() -> None:
    tenant = organization(name="Advisory", slug="advisory")
    github_installation = installation(
        organization=tenant,
        github_installation_id=7101,
        github_account_id=7201,
    )
    bound_repository = repository(
        organization=tenant,
        installation=github_installation,
        github_repository_id=7301,
        name="advisory-repository",
    )
    first = _snapshot(
        tenant=tenant,
        bound_repository=bound_repository,
        receipt=_receipt(
            tenant=tenant,
            github_installation=github_installation,
            delivery="advisory-first",
        ),
        head_sha="b" * 40,
        checksum_seed="first",
    )
    latest = _snapshot(
        tenant=tenant,
        bound_repository=bound_repository,
        receipt=_receipt(
            tenant=tenant,
            github_installation=github_installation,
            delivery="advisory-latest",
        ),
        head_sha="c" * 40,
        checksum_seed="latest",
    )
    publisher = FakeGitHubAdvisoryPublisher()

    with pytest.raises(StaleSnapshotError):
        publish_snapshot_advisory(
            snapshot=first,
            publisher=publisher,
            dashboard_base_url="https://releaseproof.example/",
        )
    published = publish_snapshot_advisory(
        snapshot=latest,
        publisher=publisher,
        dashboard_base_url="https://releaseproof.example/",
    )
    assert published.external_id == "fake-check-1"
    assert published.report.conclusion == AdvisoryConclusion.NEUTRAL
    assert published.report.producer_version == "m2-snapshot-receipt-v1"
    assert "not available" in published.report.summary
    assert str(latest.public_id) in published.report.details_url
