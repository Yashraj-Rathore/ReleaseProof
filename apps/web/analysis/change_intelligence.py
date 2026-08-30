"""Tenant-scoped persistence orchestration for deterministic M3 analysis."""

from __future__ import annotations

import uuid

from django.db import IntegrityError, transaction

from apps.web.changes.models import ChangeFeatureSet, PullRequestSnapshot
from apps.web.evidence.models import EvidenceItem, EvidenceKind
from apps.web.organizations.models import Organization
from apps.web.risk.services import persist_deterministic_score
from packages.change_intel import (
    EVIDENCE_SCHEMA_VERSION,
    EXTRACTOR_VERSION,
    FEATURE_SCHEMA_VERSION,
    HistoricalChange,
    HistoricalFileChange,
    RawChangedFile,
    SourceTree,
    SourceTreeProvider,
    SourceTreeProviderError,
    analyze_change,
)
from packages.github_contracts import ChangedFile, CheckRun

MAX_PERSISTED_HISTORY = 10_000
MAX_EVIDENCE_FACTORS = 2_500
_FAILURE_CONCLUSIONS = {"failure", "timed_out", "action_required", "cancelled"}
_OBSERVED_CONCLUSIONS = _FAILURE_CONCLUSIONS | {"success", "neutral", "skipped"}


def _raw_files(snapshot: PullRequestSnapshot) -> tuple[RawChangedFile, ...]:
    files: list[RawChangedFile] = []
    for value in snapshot.changed_files:
        changed = ChangedFile(
            path=value["path"],
            additions=value["additions"],
            deletions=value["deletions"],
            status=value["status"],
            previous_path=value.get("previous_path"),
            patch=value.get("patch"),
        )
        files.append(
            RawChangedFile(
                path=changed.path,
                additions=changed.additions,
                deletions=changed.deletions,
                status=changed.status,
                previous_path=changed.previous_path,
                patch=changed.patch,
            )
        )
    return tuple(files)


def _failure_proxy(snapshot: PullRequestSnapshot) -> bool | None:
    conclusions: set[str] = set()
    for value in snapshot.checks:
        check = CheckRun(
            name=value["name"],
            status=value["status"],
            conclusion=value.get("conclusion"),
        )
        if check.conclusion is not None:
            conclusions.add(check.conclusion)
    if conclusions & _FAILURE_CONCLUSIONS:
        return True
    if conclusions & _OBSERVED_CONCLUSIONS:
        return False
    return None


def _history_change(snapshot: PullRequestSnapshot) -> HistoricalChange:
    return HistoricalChange(
        observed_at=snapshot.created_at,
        files=tuple(
            HistoricalFileChange(
                path=changed.path,
                additions=changed.additions,
                deletions=changed.deletions,
            )
            for changed in _raw_files(snapshot)
        ),
        author_key=snapshot.author_key,
        failed_check_proxy=_failure_proxy(snapshot),
    )


def _source_tree(
    *,
    snapshot: PullRequestSnapshot,
    provider: SourceTreeProvider | None,
) -> SourceTree | None:
    if provider is None:
        return None
    try:
        tree = provider.get_tree(
            repository_key=snapshot.repository.full_name,
            revision=snapshot.base_sha,
        )
    except SourceTreeProviderError:
        return None
    if tree.repository_key != snapshot.repository.full_name or tree.revision != snapshot.base_sha:
        raise ValueError("source tree identity does not match the immutable snapshot")
    return tree


def _existing_feature_set(
    *, organization: Organization, snapshot: PullRequestSnapshot
) -> ChangeFeatureSet | None:
    return (
        ChangeFeatureSet.objects.for_organization(organization)
        .filter(
            snapshot=snapshot,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            extractor_version=EXTRACTOR_VERSION,
        )
        .first()
    )


def analyze_snapshot_for_organization(
    *,
    organization: Organization,
    snapshot_public_id: uuid.UUID | str,
    source_tree_provider: SourceTreeProvider | None = None,
) -> tuple[ChangeFeatureSet, bool]:
    snapshot = (
        PullRequestSnapshot.objects.select_related("repository")
        .filter(
            organization=organization,
            public_id=snapshot_public_id,
        )
        .first()
    )
    if snapshot is None:
        raise ValueError("snapshot is unavailable in the active organization")
    existing = _existing_feature_set(organization=organization, snapshot=snapshot)
    if existing is not None:
        persist_deterministic_score(organization=organization, feature_set=existing)
        return existing, False

    history_rows = list(
        PullRequestSnapshot.objects.filter(
            organization=organization,
            repository=snapshot.repository,
            created_at__lt=snapshot.created_at,
        ).order_by("created_at", "id")[: MAX_PERSISTED_HISTORY + 1]
    )
    history_truncated = len(history_rows) > MAX_PERSISTED_HISTORY
    history_rows = history_rows[-MAX_PERSISTED_HISTORY:]
    result = analyze_change(
        changed_files=_raw_files(snapshot),
        prediction_time=snapshot.created_at,
        history=tuple(_history_change(row) for row in history_rows),
        source_tree=_source_tree(snapshot=snapshot, provider=source_tree_provider),
        current_author_key=snapshot.author_key,
        commit_count=snapshot.commit_count,
        history_truncated=history_truncated,
    )
    if len(result.risk_factors) > MAX_EVIDENCE_FACTORS:
        raise ValueError("deterministic evidence exceeds the persistence limit")

    try:
        with transaction.atomic():
            feature_set = ChangeFeatureSet(
                organization=organization,
                snapshot=snapshot,
                prediction_time=snapshot.created_at,
                diff_schema_version=result.normalized_diff.schema_version,
                feature_schema_version=result.features.schema_version,
                extractor_version=result.features.extractor_version,
                graph_schema_version=result.graph.schema_version,
                history_schema_version=result.history.schema_version,
                evidence_schema_version=EVIDENCE_SCHEMA_VERSION,
                normalized_diff=result.normalized_diff.as_dict(),
                diff_hash=result.normalized_diff.diff_hash,
                feature_values=result.features.values,
                feature_missing=result.features.missing,
                feature_provenance=result.features.provenance,
                feature_hash=result.features.feature_hash,
                graph=result.graph.as_dict(),
                graph_hash=result.graph.graph_hash,
                blast_radius=result.blast_radius.as_dict(),
                historical_statistics=result.history.as_dict(),
                result_hash=result.result_hash,
            )
            feature_set.full_clean()
            feature_set.save()
            evidence_items: list[EvidenceItem] = []
            for sequence, factor in enumerate(result.risk_factors):
                evidence = EvidenceItem(
                    organization=organization,
                    snapshot=snapshot,
                    feature_set=feature_set,
                    sequence=sequence,
                    kind=EvidenceKind.DETERMINISTIC,
                    rule_id=factor.rule_id,
                    title=factor.title,
                    value=factor.value,
                    reason=factor.reason,
                    source_refs=list(factor.source_refs),
                    missing=factor.missing,
                    producer_version=EXTRACTOR_VERSION,
                    schema_version=EVIDENCE_SCHEMA_VERSION,
                )
                evidence.full_clean()
                evidence_items.append(evidence)
            EvidenceItem.objects.bulk_create(evidence_items)
            persist_deterministic_score(organization=organization, feature_set=feature_set)
            return feature_set, True
    except IntegrityError:
        existing = _existing_feature_set(organization=organization, snapshot=snapshot)
        if existing is None:
            raise
        persist_deterministic_score(organization=organization, feature_set=existing)
        return existing, False
