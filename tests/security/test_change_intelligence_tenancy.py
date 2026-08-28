from __future__ import annotations

import hashlib

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction

from apps.web.analysis.change_intelligence import analyze_snapshot_for_organization
from apps.web.changes.models import ChangeFeatureSet
from apps.web.evidence.models import EvidenceItem, EvidenceKind
from tests.factories import installation, organization, repository
from tests.integration.test_change_intelligence_persistence import _snapshot

pytestmark = pytest.mark.django_db


def test_feature_and_evidence_services_and_constraints_reject_cross_tenant_access() -> None:
    tenant_a = organization(name="M3 Tenant A", slug="m3-a")
    tenant_b = organization(name="M3 Tenant B", slug="m3-b")
    install_a = installation(
        organization=tenant_a,
        github_installation_id=5101,
        github_account_id=5201,
    )
    repo_a = repository(
        organization=tenant_a,
        installation=install_a,
        github_repository_id=5301,
        name="releaseproof",
    )
    snapshot_a = _snapshot(
        tenant=tenant_a,
        github_installation=install_a,
        bound_repository=repo_a,
        label="5",
        path="src/fixture_app/pricing.py",
        author_key=None,
        failed=None,
    )

    with pytest.raises(ValueError, match="active organization"):
        analyze_snapshot_for_organization(
            organization=tenant_b,
            snapshot_public_id=snapshot_a.public_id,
        )
    feature_set, created = analyze_snapshot_for_organization(
        organization=tenant_a,
        snapshot_public_id=snapshot_a.public_id,
    )
    assert created is True

    with (
        pytest.raises(DatabaseError, match="tenant relationship mismatch"),
        transaction.atomic(),
    ):
        ChangeFeatureSet.objects.create(
            organization=tenant_b,
            snapshot=snapshot_a,
            prediction_time=snapshot_a.created_at,
            diff_schema_version=feature_set.diff_schema_version,
            feature_schema_version=feature_set.feature_schema_version,
            extractor_version="cross-tenant-attempt-v1",
            graph_schema_version=feature_set.graph_schema_version,
            history_schema_version=feature_set.history_schema_version,
            evidence_schema_version=feature_set.evidence_schema_version,
            normalized_diff=feature_set.normalized_diff,
            diff_hash=feature_set.diff_hash,
            feature_values=feature_set.feature_values,
            feature_missing=feature_set.feature_missing,
            feature_provenance=feature_set.feature_provenance,
            feature_hash=feature_set.feature_hash,
            graph=feature_set.graph,
            graph_hash=feature_set.graph_hash,
            blast_radius=feature_set.blast_radius,
            historical_statistics=feature_set.historical_statistics,
            result_hash=hashlib.sha256(b"cross-tenant").hexdigest(),
        )

    with (
        pytest.raises(DatabaseError, match="tenant relationship mismatch"),
        transaction.atomic(),
    ):
        EvidenceItem.objects.create(
            organization=tenant_b,
            snapshot=snapshot_a,
            feature_set=feature_set,
            sequence=10_000,
            kind=EvidenceKind.DETERMINISTIC,
            rule_id="cross-tenant-attempt-v1",
            title="Rejected cross-tenant evidence",
            value=None,
            reason="This row must never persist.",
            source_refs=["fixture"],
            missing=True,
            producer_version="cross-tenant-attempt-v1",
            schema_version="cross-tenant-attempt-v1",
        )


def test_feature_and_evidence_records_are_append_only_in_code_and_database() -> None:
    tenant = organization(name="M3 Immutable", slug="m3-immutable")
    github_installation = installation(
        organization=tenant,
        github_installation_id=6101,
        github_account_id=6201,
    )
    bound_repository = repository(
        organization=tenant,
        installation=github_installation,
        github_repository_id=6301,
        name="releaseproof",
    )
    snapshot = _snapshot(
        tenant=tenant,
        github_installation=github_installation,
        bound_repository=bound_repository,
        label="6",
        path="src/fixture_app/pricing.py",
        author_key=None,
        failed=None,
    )
    feature_set, _created = analyze_snapshot_for_organization(
        organization=tenant,
        snapshot_public_id=snapshot.public_id,
    )
    evidence = EvidenceItem.objects.filter(feature_set=feature_set).first()
    assert evidence is not None

    with pytest.raises(ValidationError, match="immutable"):
        ChangeFeatureSet.objects.filter(pk=feature_set.pk).update(result_hash="0" * 64)
    with pytest.raises(ValidationError, match="immutable"):
        EvidenceItem.objects.filter(pk=evidence.pk).delete()
    with (
        pytest.raises(DatabaseError, match="immutable"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE changes_changefeatureset SET result_hash = %s WHERE id = %s",
            ["0" * 64, feature_set.pk],
        )
