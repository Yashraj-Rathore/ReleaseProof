"""Append-only, tenant-bound deterministic and later-stage evidence records."""

from __future__ import annotations

import uuid
from typing import Any, NoReturn

from django.core.exceptions import ValidationError
from django.db import models

from apps.web.changes.models import ChangeFeatureSet, ImmutableQuerySet, PullRequestSnapshot
from apps.web.organizations.models import Organization


def validate_source_refs(value: Any) -> None:
    if (
        not isinstance(value, list)
        or len(value) > 64
        or not all(
            isinstance(item, str) and 1 <= len(item.encode("utf-8")) <= 1_200 and "\x00" not in item
            for item in value
        )
    ):
        raise ValidationError("evidence source references must be a bounded string list")


class EvidenceKind(models.TextChoices):
    DETERMINISTIC = "deterministic", "Deterministic"
    ML = "ml", "Machine learning"
    RETRIEVAL = "retrieval", "Retrieval"
    LLM = "llm", "LLM"
    TEST = "test", "Test"
    EXECUTION = "execution", "Execution"
    SECURITY = "security", "Security"
    UNKNOWN = "unknown", "Unknown"


class EvidenceItemQuerySet(ImmutableQuerySet["EvidenceItem"]):
    def for_organization(self, organization: Organization | int) -> EvidenceItemQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class EvidenceItem(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="evidence_items",
    )
    snapshot = models.ForeignKey(
        PullRequestSnapshot,
        on_delete=models.PROTECT,
        related_name="evidence_items",
    )
    feature_set = models.ForeignKey(
        ChangeFeatureSet,
        on_delete=models.PROTECT,
        related_name="evidence_items",
    )
    sequence = models.PositiveIntegerField()
    kind = models.CharField(max_length=32, choices=EvidenceKind)
    rule_id = models.CharField(max_length=160)
    title = models.CharField(max_length=256)
    value = models.JSONField(null=True, blank=True)
    reason = models.CharField(max_length=512)
    source_refs = models.JSONField(default=list, validators=[validate_source_refs])
    missing = models.BooleanField(default=False)
    producer_version = models.CharField(max_length=64)
    schema_version = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = EvidenceItemQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="evidence_item_org_id_unique",
            ),
            models.UniqueConstraint(
                fields=("feature_set", "sequence"),
                name="evidence_item_feature_sequence_unique",
            ),
        ]
        ordering = ("feature_set", "sequence")

    def clean(self) -> None:
        super().clean()
        if self.organization_id is None or self.snapshot_id is None or self.feature_set_id is None:
            return
        if self.snapshot.organization_id != self.organization_id:
            raise ValidationError("evidence and snapshot must share an organization")
        if self.feature_set.organization_id != self.organization_id:
            raise ValidationError("evidence and feature set must share an organization")
        if self.feature_set.snapshot_id != self.snapshot_id:
            raise ValidationError("evidence must reference its feature set snapshot")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("evidence items are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("evidence items are immutable")
