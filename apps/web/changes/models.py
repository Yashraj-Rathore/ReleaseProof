"""Append-only webhook receipts and immutable pull-request snapshots."""

from __future__ import annotations

import re
import uuid
from typing import Any, NoReturn

from django.core.exceptions import ValidationError
from django.db import models

from apps.web.organizations.models import Organization
from apps.web.repositories.models import GitHubInstallation, Repository
from packages.github_contracts import ChangedFile, CheckRun

_DELIVERY_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,100}$")
_EVENT_PATTERN = re.compile(r"^[a-z_]{1,64}$")
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")
_CHECKSUM_PATTERN = re.compile(r"^[0-9a-f]{64}$")


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
    SCHEMA_VERSION = "github-pr-snapshot-v1"

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
