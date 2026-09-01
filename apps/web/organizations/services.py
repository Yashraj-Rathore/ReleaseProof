"""Server-derived tenant context and role authorization."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.http import Http404

from apps.web.organizations.models import (
    HostedLLMPolicy,
    Membership,
    MembershipRole,
    Organization,
    OrganizationLifecycle,
    OrganizationQuerySet,
)
from apps.web.repositories.models import Repository
from packages.ai_core import (
    ContentClass,
    PrivacyPolicySnapshot,
    RetentionMode,
    RoutingMode,
    TrainingUseMode,
)

ROLE_RANK = {
    MembershipRole.READ_ONLY: 0,
    MembershipRole.MEMBER: 1,
    MembershipRole.REVIEWER: 2,
    MembershipRole.ADMIN: 3,
    MembershipRole.OWNER: 4,
}


def organizations_for_user(
    user: AbstractBaseUser | AnonymousUser,
) -> OrganizationQuerySet:
    if not user.is_authenticated or user.pk is None:
        return Organization.objects.none()
    return Organization.objects.active().for_user(int(user.pk))


def require_organization(
    user: AbstractBaseUser | AnonymousUser,
    organization_public_id: uuid.UUID | str,
) -> Organization:
    if not user.is_authenticated or user.pk is None:
        raise Http404("organization not found")
    try:
        public_id = uuid.UUID(str(organization_public_id))
    except ValueError as error:
        raise Http404("organization not found") from error
    try:
        return Organization.objects.active().for_user(int(user.pk)).get(public_id=public_id)
    except Organization.DoesNotExist as error:
        raise Http404("organization not found") from error


def require_membership_role(
    *,
    user: AbstractBaseUser | AnonymousUser,
    organization: Organization,
    allowed_roles: Iterable[MembershipRole],
) -> Membership:
    if not user.is_authenticated or user.pk is None:
        raise Http404("organization not found")
    allowed = {str(role) for role in allowed_roles}
    try:
        return (
            Membership.objects.active()
            .for_organization(organization)
            .get(
                user_id=user.pk,
                role__in=allowed,
                organization__lifecycle=OrganizationLifecycle.ACTIVE,
            )
        )
    except Membership.DoesNotExist as error:
        raise Http404("organization not found") from error


def require_minimum_role(
    *,
    user: AbstractBaseUser | AnonymousUser,
    organization: Organization,
    minimum_role: MembershipRole,
) -> Membership:
    membership = require_membership_role(
        user=user,
        organization=organization,
        allowed_roles=MembershipRole,
    )
    if ROLE_RANK[MembershipRole(membership.role)] < ROLE_RANK[minimum_role]:
        raise Http404("organization not found")
    return membership


def resolve_effective_llm_policy(
    *,
    organization: Organization,
    repository: Repository,
) -> HostedLLMPolicy | None:
    """Resolve the newest immutable repository override, then organization default."""

    if repository.organization_id != organization.id:
        raise ValueError("repository is unavailable in the active organization")
    scoped = HostedLLMPolicy.objects.for_organization(organization)
    repository_policy = scoped.filter(repository=repository).order_by("-version", "-id").first()
    if repository_policy is not None:
        return repository_policy
    return scoped.filter(repository__isnull=True).order_by("-version", "-id").first()


def llm_policy_snapshot(policy: HostedLLMPolicy) -> PrivacyPolicySnapshot:
    """Hash the complete safe policy decision input without source or credentials."""

    payload = {
        "policy_id": str(policy.public_id),
        "version": policy.version,
        "schema_version": policy.schema_version,
        "scope": "repository" if policy.repository_id is not None else "organization",
        "repository_id": (
            str(policy.repository.public_id)
            if policy.repository_id is not None and policy.repository is not None
            else None
        ),
        "routing_mode": policy.routing_mode,
        "allowed_providers": policy.allowed_providers,
        "allowed_models": policy.allowed_models,
        "allowed_content_classes": policy.allowed_content_classes,
        "max_transmitted_bytes": policy.max_transmitted_bytes,
        "max_input_tokens": policy.max_input_tokens,
        "max_output_tokens": policy.max_output_tokens,
        "max_cost_microusd": policy.max_cost_microusd,
        "redaction_version": policy.redaction_version,
        "training_use_mode": policy.training_use_mode,
        "terms_reviewed_on": (
            policy.terms_reviewed_on.isoformat() if policy.terms_reviewed_on else None
        ),
        "retention_mode": policy.retention_mode,
        "retention_days": policy.retention_days,
        "allowed_regions": policy.allowed_regions,
        "response_storage_disabled": policy.response_storage_disabled,
        "approved_by_role": policy.approved_by_role,
        "connect_timeout_seconds": policy.connect_timeout_seconds,
        "read_timeout_seconds": policy.read_timeout_seconds,
        "max_attempts": policy.max_attempts,
        "retry_backoff_seconds": policy.retry_backoff_seconds,
    }
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return PrivacyPolicySnapshot(
        policy_id=str(policy.public_id),
        policy_version=policy.version,
        policy_sha256=hashlib.sha256(encoded).hexdigest(),
        routing_mode=RoutingMode(policy.routing_mode),
        allowed_providers=tuple(str(value) for value in policy.allowed_providers),
        allowed_models=tuple(str(value) for value in policy.allowed_models),
        allowed_content_classes=tuple(
            ContentClass(str(value)) for value in policy.allowed_content_classes
        ),
        max_transmitted_bytes=policy.max_transmitted_bytes,
        max_input_tokens=policy.max_input_tokens,
        max_output_tokens=policy.max_output_tokens,
        max_cost_microusd=policy.max_cost_microusd,
        redaction_version=policy.redaction_version,
        training_use_mode=TrainingUseMode(policy.training_use_mode),
        terms_reviewed_on=policy.terms_reviewed_on,
        retention_mode=RetentionMode(policy.retention_mode),
        retention_days=policy.retention_days,
        allowed_regions=tuple(str(value) for value in policy.allowed_regions),
        response_storage_disabled=policy.response_storage_disabled,
        connect_timeout_seconds=policy.connect_timeout_seconds,
        read_timeout_seconds=policy.read_timeout_seconds,
        max_attempts=policy.max_attempts,
        retry_backoff_seconds=policy.retry_backoff_seconds,
    )
