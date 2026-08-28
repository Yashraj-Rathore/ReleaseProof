from __future__ import annotations

import hashlib
import uuid
from dataclasses import replace

import pytest
from django.db import transaction

from adapters.change_intel import FakeSourceTreeProvider
from apps.web.analysis.models import JobState, JobType
from apps.web.analysis.services import create_job_with_outbox, process_ingestion_job
from apps.web.changes.models import ChangeFeatureSet, PullRequestSnapshot, WebhookReceipt
from apps.web.evidence.models import EvidenceItem, EvidenceKind
from apps.web.organizations.models import Organization
from apps.web.repositories.models import GitHubInstallation, Repository
from packages.change_intel import EXTRACTOR_VERSION, FEATURE_SCHEMA_VERSION
from tests.change_intel_fixtures import BASE_SHA, fixture_source_tree
from tests.factories import installation, organization, repository

pytestmark = pytest.mark.django_db


def _binding() -> tuple[Organization, GitHubInstallation, Repository]:
    tenant = organization(name="M3 Tenant", slug="m3-tenant")
    github_installation = installation(
        organization=tenant,
        github_installation_id=4101,
        github_account_id=4201,
    )
    bound_repository = repository(
        organization=tenant,
        installation=github_installation,
        github_repository_id=4301,
        name="releaseproof",
    )
    return tenant, github_installation, bound_repository


def _snapshot(
    *,
    tenant: Organization,
    github_installation: GitHubInstallation,
    bound_repository: Repository,
    label: str,
    path: str,
    author_key: str | None,
    failed: bool | None,
) -> PullRequestSnapshot:
    receipt = WebhookReceipt.objects.create(
        organization=tenant,
        installation=github_installation,
        delivery_id=f"m3-{label}",
        event_name="pull_request",
        action="opened",
        payload_sha256=hashlib.sha256(f"payload-{label}".encode()).hexdigest(),
        payload_size=100,
    )
    checks: list[dict[str, str | None]] = []
    if failed is not None:
        checks.append(
            {
                "name": "fixture-tests",
                "status": "completed",
                "conclusion": "failure" if failed else "success",
            }
        )
    snapshot = PullRequestSnapshot(
        organization=tenant,
        repository=bound_repository,
        first_receipt=receipt,
        pull_request_number=int(label),
        title=f"Synthetic change {label}",
        base_ref="main",
        head_ref=f"feature/{label}",
        base_sha=BASE_SHA,
        head_sha=f"{int(label):040x}",
        author_key=author_key,
        commit_count=2,
        changed_files=[
            {
                "path": path,
                "additions": 4,
                "deletions": 1,
                "status": "modified",
                "previous_path": None,
                "patch": "@@ -1 +1 @@\n-old\n+new",
            }
        ],
        checks=checks,
        snapshot_checksum=hashlib.sha256(f"snapshot-{label}".encode()).hexdigest(),
    )
    snapshot.full_clean()
    snapshot.save()
    return snapshot


def test_durable_job_persists_versioned_features_graph_history_and_evidence() -> None:
    tenant, github_installation, bound_repository = _binding()
    _snapshot(
        tenant=tenant,
        github_installation=github_installation,
        bound_repository=bound_repository,
        label="1",
        path="src/fixture_app/pricing.py",
        author_key="fixture-author",
        failed=True,
    )
    target = _snapshot(
        tenant=tenant,
        github_installation=github_installation,
        bound_repository=bound_repository,
        label="2",
        path="src/fixture_app/pricing.py",
        author_key="fixture-author",
        failed=None,
    )
    _snapshot(
        tenant=tenant,
        github_installation=github_installation,
        bound_repository=bound_repository,
        label="3",
        path="src/fixture_app/pricing.py",
        author_key="fixture-author",
        failed=True,
    )
    with transaction.atomic():
        job, _created = create_job_with_outbox(
            organization=tenant,
            job_type=JobType.PULL_REQUEST_SNAPSHOT,
            idempotency_key=f"m3:{target.snapshot_checksum}",
            correlation_id=uuid.uuid4(),
            snapshot=target,
        )
    provider = FakeSourceTreeProvider(
        [replace(fixture_source_tree(), repository_key=bound_repository.full_name)]
    )

    assert (
        process_ingestion_job(
            organization_public_id=str(tenant.public_id),
            job_public_id=str(job.public_id),
            source_tree_provider=provider,
        )
        == "completed"
    )
    assert (
        process_ingestion_job(
            organization_public_id=str(tenant.public_id),
            job_public_id=str(job.public_id),
            source_tree_provider=provider,
        )
        == "duplicate"
    )

    job.refresh_from_db()
    feature_set = ChangeFeatureSet.objects.get(snapshot=target)
    evidence = EvidenceItem.objects.filter(feature_set=feature_set)
    assert job.state == JobState.COMPLETED
    assert job.outcome_code == "change_intelligence_complete"
    assert feature_set.feature_schema_version == FEATURE_SCHEMA_VERSION
    assert feature_set.extractor_version == EXTRACTOR_VERSION
    assert feature_set.graph["available"] is True
    assert feature_set.feature_values["blast_direct_modules"] == 2
    assert feature_set.feature_values["prior_failure_proxy_count_90d"] == 1
    assert feature_set.feature_values["ownership_familiarity_90d"] == 1.0
    assert feature_set.historical_statistics["included_changes"] == 1
    assert feature_set.historical_statistics["excluded_future_changes"] == 0
    assert "score" not in feature_set.feature_values
    assert evidence.count() > len(feature_set.feature_values)
    assert evidence.filter(kind=EvidenceKind.DETERMINISTIC).count() == evidence.count()
    assert not evidence.filter(rule_id__icontains="score").exists()
    assert provider.requests == [(bound_repository.full_name, BASE_SHA)]


def test_missing_source_tree_persists_explicit_missingness_without_guessing() -> None:
    tenant, github_installation, bound_repository = _binding()
    target = _snapshot(
        tenant=tenant,
        github_installation=github_installation,
        bound_repository=bound_repository,
        label="4",
        path="src/fixture_app/pricing.py",
        author_key=None,
        failed=None,
    )
    with transaction.atomic():
        job, _created = create_job_with_outbox(
            organization=tenant,
            job_type=JobType.PULL_REQUEST_SNAPSHOT,
            idempotency_key=f"m3:{target.snapshot_checksum}",
            correlation_id=uuid.uuid4(),
            snapshot=target,
        )

    assert (
        process_ingestion_job(
            organization_public_id=str(tenant.public_id),
            job_public_id=str(job.public_id),
        )
        == "completed"
    )
    job.refresh_from_db()
    feature_set = ChangeFeatureSet.objects.get(snapshot=target)
    assert job.outcome_code == "change_intelligence_partial"
    assert feature_set.graph["available"] is False
    assert feature_set.feature_values["blast_direct_modules"] is None
    assert "blast_direct_modules" in feature_set.feature_missing
    assert feature_set.feature_values["historical_file_touches_90d"] is None
    assert "historical_file_touches_90d" in feature_set.feature_missing
    assert feature_set.feature_values["ownership_familiarity_90d"] is None
    assert EvidenceItem.objects.filter(feature_set=feature_set, missing=True).exists()
