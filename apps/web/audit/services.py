"""Safe audit-record creation."""

from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth.models import AbstractBaseUser

from apps.web.audit.models import AuditLog
from apps.web.organizations.models import Organization


def record_audit(
    *,
    organization: Organization,
    action: str,
    resource_type: str,
    resource_public_id: uuid.UUID,
    correlation_id: uuid.UUID,
    actor: AbstractBaseUser | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    audit_log = AuditLog(
        organization=organization,
        actor_id=actor.pk if actor is not None else None,
        action=action,
        resource_type=resource_type,
        resource_public_id=resource_public_id,
        correlation_id=correlation_id,
        metadata=metadata or {},
    )
    audit_log.full_clean()
    audit_log.save()
    return audit_log
