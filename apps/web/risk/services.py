"""Tenant-scoped deterministic risk-score persistence and retrieval."""

from __future__ import annotations

import uuid

from django.db import IntegrityError, transaction
from django.http import Http404

from apps.web.changes.models import ChangeFeatureSet, PullRequestSnapshot
from apps.web.organizations.models import Organization
from apps.web.risk.models import RiskScore
from packages.ml_core import (
    BASELINE_ARTIFACT_VERSION,
    THRESHOLD_POLICY_VERSION,
    baseline_artifact_hash,
    score_features,
)


def _existing_score(
    *, organization: Organization, feature_set: ChangeFeatureSet
) -> RiskScore | None:
    return (
        RiskScore.objects.for_organization(organization)
        .filter(
            feature_set=feature_set,
            artifact_version=BASELINE_ARTIFACT_VERSION,
            artifact_hash=baseline_artifact_hash(),
            threshold_policy_version=THRESHOLD_POLICY_VERSION,
        )
        .first()
    )


def persist_deterministic_score(
    *,
    organization: Organization,
    feature_set: ChangeFeatureSet,
) -> tuple[RiskScore, bool]:
    if feature_set.organization_id != organization.id:
        raise ValueError("feature set is unavailable in the active organization")
    existing = _existing_score(organization=organization, feature_set=feature_set)
    if existing is not None:
        return existing, False
    score = score_features(
        feature_schema_version=feature_set.feature_schema_version,
        values=feature_set.feature_values,
    )
    try:
        with transaction.atomic():
            record = RiskScore(
                organization=organization,
                snapshot=feature_set.snapshot,
                feature_set=feature_set,
                schema_version=score.schema_version,
                artifact_version=score.artifact_version,
                artifact_hash=score.artifact_hash,
                feature_schema_version=score.feature_schema_version,
                threshold_policy_version=score.threshold_policy_version,
                threshold=score.threshold,
                raw_score=score.score,
                calibrated_probability=None,
                band=score.band,
                proxy_prediction=score.proxy_prediction,
                contributions=[item.as_dict() for item in score.contributions],
                missing_required=list(score.missing_required),
                result_hash=score.result_hash,
            )
            record.full_clean()
            record.save()
            return record, True
    except IntegrityError:
        existing = _existing_score(organization=organization, feature_set=feature_set)
        if existing is None:
            raise
        return existing, False


def get_current_risk_score(
    *,
    organization: Organization,
    snapshot_public_id: uuid.UUID,
) -> RiskScore:
    snapshot = (
        PullRequestSnapshot.objects.filter(
            organization_id=organization.id,
            public_id=snapshot_public_id,
        )
        .only("id")
        .first()
    )
    if snapshot is None:
        raise Http404("snapshot not found")
    score = (
        RiskScore.objects.for_organization(organization)
        .filter(
            snapshot_id=snapshot.id,
            artifact_version=BASELINE_ARTIFACT_VERSION,
            artifact_hash=baseline_artifact_hash(),
            threshold_policy_version=THRESHOLD_POLICY_VERSION,
        )
        .first()
    )
    if score is None:
        raise Http404("risk score not found")
    return score


def serialize_risk_score(score: RiskScore) -> dict[str, object]:
    return {
        "artifact_hash": score.artifact_hash,
        "artifact_version": score.artifact_version,
        "band": score.band,
        "calibrated_probability": None,
        "contributions": score.contributions,
        "created_at": score.created_at.isoformat(),
        "feature_schema_version": score.feature_schema_version,
        "missing_required": score.missing_required,
        "probability_display_allowed": False,
        "proxy_prediction": score.proxy_prediction,
        "raw_score": score.raw_score,
        "result_hash": score.result_hash,
        "schema_version": "risk-model-response-v1",
        "snapshot_id": str(score.snapshot.public_id),
        "threshold": score.threshold,
        "threshold_policy_version": score.threshold_policy_version,
    }
