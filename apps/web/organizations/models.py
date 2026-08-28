"""Tenant and membership persistence owned by the organizations module."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class OrganizationLifecycle(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    DELETING = "deleting", "Deleting"
    DELETED = "deleted", "Deleted"


class MembershipRole(models.TextChoices):
    OWNER = "owner", "Owner"
    ADMIN = "admin", "Admin"
    REVIEWER = "reviewer", "Reviewer"
    MEMBER = "member", "Member"
    READ_ONLY = "read_only", "Read only"


class MembershipLifecycle(models.TextChoices):
    ACTIVE = "active", "Active"
    REVOKED = "revoked", "Revoked"


class OrganizationQuerySet(models.QuerySet["Organization"]):
    def active(self) -> OrganizationQuerySet:
        return self.filter(lifecycle=OrganizationLifecycle.ACTIVE)

    def for_user(self, user_id: int) -> OrganizationQuerySet:
        return self.filter(
            memberships__user_id=user_id,
            memberships__lifecycle=MembershipLifecycle.ACTIVE,
        ).distinct()


class Organization(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    lifecycle = models.CharField(
        max_length=16,
        choices=OrganizationLifecycle,
        default=OrganizationLifecycle.ACTIVE,
    )
    hosted_llm_enabled = models.BooleanField(default=False)
    organization_learning_enabled = models.BooleanField(default=False)
    metadata_retention_days = models.PositiveIntegerField(
        default=365,
        validators=[MinValueValidator(1), MaxValueValidator(3_650)],
    )
    policy_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("id", "public_id"),
                name="organizations_org_id_public_unique",
            )
        ]
        ordering = ("name", "id")

    def __str__(self) -> str:
        return self.name


class MembershipQuerySet(models.QuerySet["Membership"]):
    def active(self) -> MembershipQuerySet:
        return self.filter(lifecycle=MembershipLifecycle.ACTIVE)

    def for_organization(self, organization: Organization | int) -> MembershipQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class Membership(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="releaseproof_memberships",
    )
    role = models.CharField(max_length=16, choices=MembershipRole)
    lifecycle = models.CharField(
        max_length=16,
        choices=MembershipLifecycle,
        default=MembershipLifecycle.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MembershipQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "user"),
                name="organizations_membership_org_user_unique",
            ),
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="organizations_membership_org_id_unique",
            ),
        ]
        ordering = ("organization_id", "id")

    def __str__(self) -> str:
        return f"{self.organization_id}:{self.user_id}:{self.role}"
