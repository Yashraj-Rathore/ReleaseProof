"""Append-only webhook receipts and immutable pull-request snapshots."""

from __future__ import annotations

import re
import uuid
from typing import Any, NoReturn

from django.core.exceptions import ValidationError
from django.db import models

from apps.web.organizations.models import Organization
from apps.web.repositories.models import GitHubInstallation, Repository
from packages.change_intel import (
    EVIDENCE_SCHEMA_VERSION,
    FEATURE_DEFINITIONS,
    FEATURE_SCHEMA_VERSION,
)
from packages.github_contracts import ChangedFile, CheckRun

_DELIVERY_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,100}$")
_EVENT_PATTERN = re.compile(r"^[a-z_]{1,64}$")
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")
_CHECKSUM_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_AUTHOR_KEY_PATTERN = re.compile(r"^[A-Za-z0-9:_-]{1,64}$")


def validate_delivery_id(value: str) -> None:
    if not _DELIVERY_PATTERN.fullmatch(value):
        raise ValidationError("delivery ID is outside the bounded contract")


def validate_event_name(value: str) -> None:
    if not _EVENT_PATTERN.fullmatch(value):
        raise ValidationError("event name is outside the bounded contract")


def validate_sha(value: str) -> None:
    if not _SHA_PATTERN.fullmatch(value):
        raise ValidationError("commit SHA is outside the bounded contract")


def validate_checksum(value: str) -> None:
    if not _CHECKSUM_PATTERN.fullmatch(value):
        raise ValidationError("checksum must be lowercase SHA-256 hexadecimal")


def validate_author_key(value: str) -> None:
    if value and not _AUTHOR_KEY_PATTERN.fullmatch(value):
        raise ValidationError("author key must be a bounded opaque provider key")


def validate_changed_files(value: Any) -> None:
    if not isinstance(value, list) or len(value) > 1_000:
        raise ValidationError("changed files must be a bounded list")
    try:
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("changed file must be an object")
            ChangedFile(
                path=item["path"],
                additions=item["additions"],
                deletions=item["deletions"],
                status=item["status"],
                previous_path=item.get("previous_path"),
                patch=item.get("patch"),
            )
    except (KeyError, TypeError, ValueError) as error:
        raise ValidationError("changed files violate the normalized schema") from error


def validate_checks(value: Any) -> None:
    if not isinstance(value, list) or len(value) > 250:
        raise ValidationError("checks must be a bounded list")
    try:
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("check must be an object")
            CheckRun(
                name=item["name"],
                status=item["status"],
                conclusion=item.get("conclusion"),
            )
    except (KeyError, TypeError, ValueError) as error:
        raise ValidationError("check metadata violates the normalized schema") from error


def validate_feature_values(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValidationError("feature values must be an object")
    definitions = {definition.name: definition for definition in FEATURE_DEFINITIONS}
    if set(value) != set(definitions):
        raise ValidationError("feature values do not match the exact schema")
    for name, feature_value in value.items():
        definition = definitions[name]
        if feature_value is None:
            if not definition.nullable:
                raise ValidationError(f"feature {name} cannot be null")
        elif definition.value_type == "integer" and (
            isinstance(feature_value, bool) or not isinstance(feature_value, int)
        ):
            raise ValidationError(f"feature {name} must be an integer")
        elif definition.value_type == "float" and (
            isinstance(feature_value, bool) or not isinstance(feature_value, (int, float))
        ):
            raise ValidationError(f"feature {name} must be a float")


def validate_feature_metadata(value: Any) -> None:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) and len(item) <= 256
        for key, item in value.items()
    ):
        raise ValidationError("feature metadata must be a bounded string mapping")
    if not set(value).issubset({definition.name for definition in FEATURE_DEFINITIONS}):
        raise ValidationError("feature metadata contains an unknown feature")


def validate_feature_provenance(value: Any) -> None:
    validate_feature_metadata(value)
    if set(value) != {definition.name for definition in FEATURE_DEFINITIONS}:
        raise ValidationError("feature provenance must cover the exact schema")


def validate_versioned_object(value: Any) -> None:
    if not isinstance(value, dict) or not ({"schema_version", "graph_schema_version"} & set(value)):
        raise ValidationError("artifact must be a versioned object")


class ImmutableQuerySet[ImmutableModel: models.Model](models.QuerySet[ImmutableModel]):
    def update(self, **kwargs: object) -> NoReturn:
        del kwargs
        raise ValidationError("immutable records cannot be updated")

    def delete(self) -> NoReturn:
        raise ValidationError("immutable records cannot be deleted")


class WebhookReceipt(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="webhook_receipts",
    )
    installation = models.ForeignKey(
        GitHubInstallation,
        on_delete=models.PROTECT,
        related_name="webhook_receipts",
    )
    delivery_id = models.CharField(max_length=100, unique=True, validators=[validate_delivery_id])
    event_name = models.CharField(max_length=64, validators=[validate_event_name])
    action = models.CharField(max_length=64)
    payload_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    payload_size = models.PositiveIntegerField()
    correlation_id = models.UUIDField(default=uuid.uuid4, editable=False)
    received_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableQuerySet["WebhookReceipt"].as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="changes_receipt_org_id_unique",
            )
        ]
        ordering = ("-received_at", "-id")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("webhook receipts are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("webhook receipts are immutable")


class PullRequestSnapshot(models.Model):
    SCHEMA_VERSION = "github-pr-snapshot-v2"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="pull_request_snapshots",
    )
    repository = models.ForeignKey(
        Repository,
        on_delete=models.PROTECT,
        related_name="pull_request_snapshots",
    )
    first_receipt = models.ForeignKey(
        WebhookReceipt,
        on_delete=models.PROTECT,
        related_name="created_snapshots",
    )
    pull_request_number = models.PositiveIntegerField()
    title = models.CharField(max_length=256)
    body = models.TextField(blank=True)
    base_ref = models.CharField(max_length=255)
    head_ref = models.CharField(max_length=255)
    base_sha = models.CharField(max_length=64, validators=[validate_sha])
    head_sha = models.CharField(max_length=64, validators=[validate_sha])
    author_key = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        validators=[validate_author_key],
    )
    commit_count = models.PositiveIntegerField(null=True, blank=True)
    changed_files = models.JSONField(default=list, blank=True, validators=[validate_changed_files])
    checks = models.JSONField(default=list, blank=True, validators=[validate_checks])
    schema_version = models.CharField(max_length=64, default=SCHEMA_VERSION, editable=False)
    snapshot_checksum = models.CharField(
        max_length=64,
        unique=True,
        validators=[validate_checksum],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableQuerySet["PullRequestSnapshot"].as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="changes_snapshot_org_id_unique",
            ),
            models.UniqueConstraint(
                fields=(
                    "repository",
                    "pull_request_number",
                    "base_sha",
                    "head_sha",
                    "schema_version",
                ),
                name="changes_snapshot_identity_unique",
            ),
        ]
        ordering = ("-created_at", "-id")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("pull-request snapshots are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("pull-request snapshots are immutable")


class ChangeFeatureSetQuerySet(ImmutableQuerySet["ChangeFeatureSet"]):
    def for_organization(self, organization: Organization | int) -> ChangeFeatureSetQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class ChangeFeatureSet(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="change_feature_sets",
    )
    snapshot = models.ForeignKey(
        PullRequestSnapshot,
        on_delete=models.PROTECT,
        related_name="feature_sets",
    )
    prediction_time = models.DateTimeField()
    diff_schema_version = models.CharField(max_length=64)
    feature_schema_version = models.CharField(max_length=64, default=FEATURE_SCHEMA_VERSION)
    extractor_version = models.CharField(max_length=64)
    graph_schema_version = models.CharField(max_length=64)
    history_schema_version = models.CharField(max_length=64)
    evidence_schema_version = models.CharField(max_length=64, default=EVIDENCE_SCHEMA_VERSION)
    normalized_diff = models.JSONField(validators=[validate_versioned_object])
    diff_hash = models.CharField(max_length=64, validators=[validate_checksum])
    feature_values = models.JSONField(validators=[validate_feature_values])
    feature_missing = models.JSONField(
        default=dict,
        blank=True,
        validators=[validate_feature_metadata],
    )
    feature_provenance = models.JSONField(validators=[validate_feature_provenance])
    feature_hash = models.CharField(max_length=64, validators=[validate_checksum])
    graph = models.JSONField(validators=[validate_versioned_object])
    graph_hash = models.CharField(max_length=64, validators=[validate_checksum])
    blast_radius = models.JSONField(validators=[validate_versioned_object])
    historical_statistics = models.JSONField(validators=[validate_versioned_object])
    result_hash = models.CharField(max_length=64, validators=[validate_checksum])
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ChangeFeatureSetQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="changes_features_org_id_unique",
            ),
            models.UniqueConstraint(
                fields=("snapshot", "feature_schema_version", "extractor_version"),
                name="changes_features_snapshot_version_unique",
            ),
            models.UniqueConstraint(
                fields=("id", "snapshot"),
                name="changes_features_id_snapshot_unique",
            ),
        ]
        ordering = ("-created_at", "-id")

    def clean(self) -> None:
        super().clean()
        if (
            self.organization_id is not None
            and self.snapshot_id is not None
            and self.snapshot.organization_id != self.organization_id
        ):
            raise ValidationError("feature set and snapshot must share an organization")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("change feature sets are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("change feature sets are immutable")
