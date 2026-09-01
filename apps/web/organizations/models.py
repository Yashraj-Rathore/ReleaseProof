"""Tenant and membership persistence owned by the organizations module."""

from __future__ import annotations

import uuid
from typing import Any, NoReturn

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from packages.ai_core import (
    POLICY_SCHEMA_VERSION,
    REDACTION_VERSION,
    ContentClass,
    RetentionMode,
    RoutingMode,
    TrainingUseMode,
)


def _validate_bounded_ascii_list(
    value: Any,
    *,
    field: str,
    maximum_items: int,
    maximum_length: int,
) -> None:
    if (
        not isinstance(value, list)
        or len(value) > maximum_items
        or len(set(value)) != len(value)
        or not all(
            isinstance(item, str)
            and 1 <= len(item) <= maximum_length
            and item.isascii()
            and all(ord(character) >= 32 for character in item)
            for item in value
        )
    ):
        raise ValidationError(f"{field} must be a bounded unique ASCII list")


def validate_llm_provider_list(value: Any) -> None:
    _validate_bounded_ascii_list(
        value, field="allowed providers", maximum_items=10, maximum_length=128
    )


def validate_llm_model_list(value: Any) -> None:
    _validate_bounded_ascii_list(
        value, field="allowed models", maximum_items=20, maximum_length=160
    )


def validate_llm_content_classes(value: Any) -> None:
    _validate_bounded_ascii_list(
        value, field="allowed content classes", maximum_items=10, maximum_length=64
    )
    if not set(value).issubset({item.value for item in ContentClass}):
        raise ValidationError("allowed content classes contain an unknown value")


def validate_llm_regions(value: Any) -> None:
    _validate_bounded_ascii_list(
        value, field="allowed regions", maximum_items=20, maximum_length=64
    )


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


class HostedLLMPolicyQuerySet(models.QuerySet["HostedLLMPolicy"]):
    def for_organization(self, organization: Organization | int) -> HostedLLMPolicyQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)

    def update(self, **kwargs: Any) -> NoReturn:
        del kwargs
        raise ValidationError("hosted LLM policies are immutable")

    def delete(self) -> NoReturn:
        raise ValidationError("hosted LLM policies are immutable")


class HostedLLMPolicy(models.Model):
    """Immutable org default or repository override for any LLM route."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="hosted_llm_policies",
    )
    repository = models.ForeignKey(
        "repositories.Repository",
        on_delete=models.PROTECT,
        related_name="hosted_llm_policies",
        null=True,
        blank=True,
    )
    version = models.PositiveIntegerField()
    schema_version = models.CharField(max_length=64, default=POLICY_SCHEMA_VERSION)
    routing_mode = models.CharField(
        max_length=32,
        choices=[(item.value, item.value) for item in RoutingMode],
        default=RoutingMode.LOCAL_ONLY,
    )
    allowed_providers = models.JSONField(default=list, validators=[validate_llm_provider_list])
    allowed_models = models.JSONField(default=list, validators=[validate_llm_model_list])
    allowed_content_classes = models.JSONField(
        default=list,
        validators=[validate_llm_content_classes],
    )
    max_transmitted_bytes = models.PositiveIntegerField(
        default=32_768,
        validators=[MinValueValidator(256), MaxValueValidator(131_072)],
    )
    max_input_tokens = models.PositiveIntegerField(
        default=49_152,
        validators=[MinValueValidator(256), MaxValueValidator(262_144)],
    )
    max_output_tokens = models.PositiveIntegerField(
        default=1_024,
        validators=[MinValueValidator(64), MaxValueValidator(8_192)],
    )
    max_cost_microusd = models.PositiveIntegerField(
        default=100_000,
        validators=[MinValueValidator(1), MaxValueValidator(100_000_000)],
    )
    redaction_version = models.CharField(max_length=64, default=REDACTION_VERSION)
    training_use_mode = models.CharField(
        max_length=32,
        choices=[(item.value, item.value) for item in TrainingUseMode],
        default=TrainingUseMode.UNKNOWN,
    )
    terms_reviewed_on = models.DateField(null=True, blank=True)
    retention_mode = models.CharField(
        max_length=40,
        choices=[(item.value, item.value) for item in RetentionMode],
        default=RetentionMode.UNKNOWN,
    )
    retention_days = models.PositiveIntegerField(null=True, blank=True)
    allowed_regions = models.JSONField(default=list, validators=[validate_llm_regions])
    response_storage_disabled = models.BooleanField(default=True)
    approved_by_role = models.CharField(
        max_length=16,
        choices=[
            (MembershipRole.OWNER, MembershipRole.OWNER.label),
            (MembershipRole.ADMIN, MembershipRole.ADMIN.label),
        ],
    )
    connect_timeout_seconds = models.FloatField(
        default=5.0,
        validators=[MinValueValidator(0.1), MaxValueValidator(60.0)],
    )
    read_timeout_seconds = models.FloatField(
        default=60.0,
        validators=[MinValueValidator(0.1), MaxValueValidator(300.0)],
    )
    max_attempts = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(3)],
    )
    retry_backoff_seconds = models.FloatField(
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(5.0)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = HostedLLMPolicyQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "repository", "id"),
                name="organizations_llm_policy_org_repo_id_unique",
            ),
            models.UniqueConstraint(
                fields=("organization", "version"),
                condition=models.Q(repository__isnull=True),
                name="organizations_llm_policy_org_version_unique",
            ),
            models.UniqueConstraint(
                fields=("repository", "version"),
                condition=models.Q(repository__isnull=False),
                name="organizations_llm_policy_repo_version_unique",
            ),
        ]
        ordering = ("organization_id", "repository_id", "version")

    def clean(self) -> None:
        super().clean()
        repository = self.repository
        if (
            self.repository_id is not None
            and repository is not None
            and repository.organization_id != self.organization_id
        ):
            raise ValidationError("LLM policy and repository organizations must match")
        if self.schema_version != POLICY_SCHEMA_VERSION:
            raise ValidationError("LLM policy schema version is unsupported")
        routing_mode = RoutingMode(self.routing_mode)
        if (
            routing_mode is RoutingMode.HOSTED_REDACTED
            and self.redaction_version != REDACTION_VERSION
        ):
            raise ValidationError("hosted redacted policy requires the supported redaction version")
        if routing_mode is not RoutingMode.LOCAL_ONLY:
            if self.terms_reviewed_on is None:
                raise ValidationError("hosted policy requires a terms review date")
            if self.training_use_mode == TrainingUseMode.UNKNOWN:
                raise ValidationError("hosted policy requires reviewed training/use terms")
            if self.retention_mode == RetentionMode.UNKNOWN:
                raise ValidationError("hosted policy requires a reviewed retention mode")
            if not self.allowed_regions:
                raise ValidationError("hosted policy requires an allowed region")
        retention_mode = RetentionMode(self.retention_mode)
        if retention_mode is RetentionMode.CONTRACTUAL_ZERO_RETENTION:
            if self.retention_days != 0:
                raise ValidationError("contractual zero retention requires zero retention days")
        elif retention_mode is RetentionMode.UNKNOWN:
            if self.retention_days is not None:
                raise ValidationError("unknown retention cannot claim a duration")
        elif self.retention_days is None:
            raise ValidationError("reviewed retention requires a duration")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("hosted LLM policies are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("hosted LLM policies are immutable")


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
