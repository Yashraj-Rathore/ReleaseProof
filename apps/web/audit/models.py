"""Append-only security and lifecycle audit records without source content."""

from __future__ import annotations

import uuid
from typing import Any, NoReturn

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.web.organizations.models import Organization


def validate_safe_metadata(value: Any) -> None:
    if not isinstance(value, dict) or len(value) > 20:
        raise ValidationError("audit metadata must be a bounded object")
    forbidden_fragments = {"token", "secret", "authorization", "cookie", "source", "patch"}
    for key, item in value.items():
        if not isinstance(key, str) or len(key) > 64:
            raise ValidationError("audit metadata keys must be bounded strings")
        if any(fragment in key.casefold() for fragment in forbidden_fragments):
            raise ValidationError("audit metadata key is not allowed")
        if not isinstance(item, (str, int, bool, type(None))) or (
            isinstance(item, str) and len(item) > 256
        ):
            raise ValidationError("audit metadata values must be bounded scalars")


class AuditLog(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="releaseproof_audit_logs",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=128)
    resource_type = models.CharField(max_length=64)
    resource_public_id = models.UUIDField()
    correlation_id = models.UUIDField()
    metadata = models.JSONField(default=dict, blank=True, validators=[validate_safe_metadata])
    occurred_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager["AuditLog"]()

    class Meta:
        ordering = ("-occurred_at", "-id")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("audit logs are append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("audit logs are append-only")
