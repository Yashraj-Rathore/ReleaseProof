"""Stale-safe advisory GitHub report publication."""

from __future__ import annotations

from urllib.parse import urljoin

from apps.web.changes.models import PullRequestSnapshot
from packages.github_contracts import (
    AdvisoryConclusion,
    AdvisoryReport,
    GitHubAdvisoryPublisher,
    PublishedAdvisory,
)


class StaleSnapshotError(RuntimeError):
    """A historical head must not overwrite output for a newer head."""


def publish_snapshot_advisory(
    *,
    snapshot: PullRequestSnapshot,
    publisher: GitHubAdvisoryPublisher,
    dashboard_base_url: str,
) -> PublishedAdvisory:
    latest = (
        PullRequestSnapshot.objects.filter(
            organization=snapshot.organization,
            repository=snapshot.repository,
            pull_request_number=snapshot.pull_request_number,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if latest is None or latest.pk != snapshot.pk:
        raise StaleSnapshotError("snapshot is no longer the latest pull-request head")
    details_url = urljoin(
        dashboard_base_url.rstrip("/") + "/",
        f"app/snapshots/{snapshot.public_id}/",
    )
    report = AdvisoryReport(
        repository_id=snapshot.repository.github_repository_id,
        pull_request_number=snapshot.pull_request_number,
        head_sha=snapshot.head_sha,
        name="ReleaseProof advisory",
        conclusion=AdvisoryConclusion.NEUTRAL,
        summary=(
            "Immutable change snapshot accepted. Risk analysis is not available until its "
            "owning milestone is implemented."
        ),
        details_url=details_url,
        producer_version="m2-snapshot-receipt-v1",
    )
    return publisher.publish(report)
