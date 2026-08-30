"""Append-only, tenant-bound deterministic and later learned risk scores."""

from __future__ import annotations

import uuid
from typing import Any, NoReturn

from django.core.exceptions import ValidationError
from django.db import models

from apps.web.changes.models import (
    ChangeFeatureSet,
    ImmutableQuerySet,
    PullRequestSnapshot,
    validate_checksum,
)
from apps.web.organizations.models import Organization
from packages.ml_core import RiskBand


def validate_contributions(value: Any) -> None:
    if not isinstance(value, list) or len(value) > 32:
        raise ValidationError("baseline contributions must be a bounded list")
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "points",
            "reason",
            "rule_id",
            "source_features",
        }:
            raise ValidationError("baseline contribution schema is invalid")
        if (
            isinstance(item["points"], bool)
            or not isinstance(item["points"], int)
            or item["points"] < 0
            or item["points"] > 100
        ):
            raise ValidationError("baseline contribution points are invalid")
        if not isinstance(item["rule_id"], str) or not 1 <= len(item["rule_id"]) <= 160:
            raise ValidationError("baseline contribution rule ID is invalid")
        if not isinstance(item["reason"], str) or not 1 <= len(item["reason"]) <= 512:
            raise ValidationError("baseline contribution reason is invalid")
        features = item["source_features"]
        if (
            not isinstance(features, list)
            or len(features) > 16
            or not all(
                isinstance(feature, str) and 1 <= len(feature) <= 128 for feature in features
            )
        ):
            raise ValidationError("baseline contribution source features are invalid")


def validate_missing_required(value: Any) -> None:
    if (
        not isinstance(value, list)
        or len(value) > 64
        or not all(isinstance(item, str) and 1 <= len(item) <= 128 for item in value)
    ):
        raise ValidationError("missing required features must be a bounded string list")


class RiskScoreQuerySet(ImmutableQuerySet["RiskScore"]):
    def for_organization(self, organization: Organization | int) -> RiskScoreQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class RiskScore(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="risk_scores",
    )
    snapshot = models.ForeignKey(
        PullRequestSnapshot,
        on_delete=models.PROTECT,
        related_name="risk_scores",
    )
    feature_set = models.ForeignKey(
        ChangeFeatureSet,
        on_delete=models.PROTECT,
        related_name="risk_scores",
    )
    schema_version = models.CharField(max_length=64)
    artifact_version = models.CharField(max_length=64)
    artifact_hash = models.CharField(max_length=64, validators=[validate_checksum])
    feature_schema_version = models.CharField(max_length=64)
    threshold_policy_version = models.CharField(max_length=64)
    threshold = models.PositiveSmallIntegerField()
    raw_score = models.PositiveSmallIntegerField(null=True, blank=True)
    calibrated_probability = models.FloatField(null=True, blank=True)
    band = models.CharField(max_length=16, choices=[(item.value, item.value) for item in RiskBand])
    proxy_prediction = models.BooleanField(null=True, blank=True)
    contributions = models.JSONField(
        default=list,
        blank=True,
        validators=[validate_contributions],
    )
    missing_required = models.JSONField(
        default=list,
        blank=True,
        validators=[validate_missing_required],
    )
    result_hash = models.CharField(max_length=64, validators=[validate_checksum])
    created_at = models.DateTimeField(auto_now_add=True)

    objects = RiskScoreQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="risk_score_org_id_unique",
            ),
            models.UniqueConstraint(
                fields=("id", "snapshot"),
                name="risk_score_id_snapshot_unique",
            ),
            models.UniqueConstraint(
                fields=(
                    "feature_set",
                    "artifact_version",
                    "artifact_hash",
                    "threshold_policy_version",
                ),
                name="risk_score_feature_artifact_unique",
            ),
        ]
        ordering = ("-created_at", "-id")

    def clean(self) -> None:
        super().clean()
        if self.calibrated_probability is not None:
            raise ValidationError("deterministic baseline scores cannot contain a probability")
        if self.threshold > 100:
            raise ValidationError("risk threshold must be between 0 and 100")
        if self.raw_score is not None and self.raw_score > 100:
            raise ValidationError("raw score must be between 0 and 100")
        if self.band == RiskBand.UNKNOWN:
            if self.raw_score is not None or self.proxy_prediction is not None:
                raise ValidationError("UNKNOWN scores cannot contain a numeric prediction")
        elif self.raw_score is None or self.proxy_prediction is None:
            raise ValidationError("known risk bands require a score and proxy prediction")
        if self.organization_id is None or self.snapshot_id is None or self.feature_set_id is None:
            return
        if self.snapshot.organization_id != self.organization_id:
            raise ValidationError("risk score and snapshot must share an organization")
        if self.feature_set.organization_id != self.organization_id:
            raise ValidationError("risk score and feature set must share an organization")
        if self.feature_set.snapshot_id != self.snapshot_id:
            raise ValidationError("risk score must reference its feature set snapshot")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("risk scores are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("risk scores are immutable")
