"""Server-derived tenant context and role authorization."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.http import Http404

from apps.web.organizations.models import (
    Membership,
    MembershipRole,
    Organization,
    OrganizationLifecycle,
    OrganizationQuerySet,
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
