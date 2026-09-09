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
from packages.observability import (
    DEFAULT_QUOTA_LIMITS,
    DEFAULT_RETENTION_DAYS,
    OPERATIONAL_POLICY_SCHEMA_VERSION,
    canonical_policy_hash,
    validate_quota_limits,
    validate_retention_days,
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


def validate_operational_quota_limits(value: Any) -> None:
    try:
        validate_quota_limits(value)
    except ValueError as error:
        raise ValidationError(str(error)) from error


def validate_operational_retention_days(value: Any) -> None:
    try:
        validate_retention_days(value)
    except ValueError as error:
        raise ValidationError(str(error)) from error


def validate_retention_candidates(value: Any) -> None:
    if not isinstance(value, dict) or len(value) > 4:
        raise ValidationError("retention candidates must be a bounded object")
    if sum(len(item) for item in value.values() if isinstance(item, list)) > 1_000:
        raise ValidationError("retention candidates exceed the per-plan bound")
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or not isinstance(item, list)
            or not all(isinstance(identifier, str) and len(identifier) == 36 for identifier in item)
        ):
            raise ValidationError("retention candidates must contain UUID strings")


def default_operational_quota_limits() -> dict[str, int]:
    return dict(DEFAULT_QUOTA_LIMITS)


def default_operational_retention_days() -> dict[str, int]:
    return dict(DEFAULT_RETENTION_DAYS)


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


class OperationalPolicyQuerySet(models.QuerySet["OperationalPolicy"]):
    def for_organization(self, organization: Organization | int) -> OperationalPolicyQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)

    def update(self, **kwargs: Any) -> NoReturn:
        del kwargs
        raise ValidationError("operational policies are immutable")

    def delete(self) -> NoReturn:
        raise ValidationError("operational policies are immutable")


class OperationalPolicy(models.Model):
    """Immutable tenant limits and retention durations; newer versions supersede by lookup."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="operational_policies",
    )
    version = models.PositiveIntegerField()
    schema_version = models.CharField(
        max_length=64, default=OPERATIONAL_POLICY_SCHEMA_VERSION, editable=False
    )
    quota_limits = models.JSONField(
        default=default_operational_quota_limits, validators=[validate_operational_quota_limits]
    )
    retention_days = models.JSONField(
        default=default_operational_retention_days,
        validators=[validate_operational_retention_days],
    )
    policy_sha256 = models.CharField(max_length=64, editable=False)
    approved_by_role = models.CharField(
        max_length=16,
        choices=[
            (MembershipRole.OWNER, MembershipRole.OWNER.label),
            (MembershipRole.ADMIN, MembershipRole.ADMIN.label),
        ],
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="releaseproof_operational_policies_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OperationalPolicyQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"), name="organizations_ops_policy_org_id_unique"
            ),
            models.UniqueConstraint(
                fields=("organization", "version"),
                name="organizations_ops_policy_org_version_unique",
            ),
            models.UniqueConstraint(
                fields=("organization", "policy_sha256"),
                name="organizations_ops_policy_org_hash_unique",
            ),
        ]
        ordering = ("organization_id", "version")

    def clean(self) -> None:
        super().clean()
        if self.schema_version != OPERATIONAL_POLICY_SCHEMA_VERSION:
            raise ValidationError("operational policy schema version is unsupported")
        try:
            quota_limits = validate_quota_limits(self.quota_limits)
            retention_days = validate_retention_days(self.retention_days)
        except ValueError as error:
            raise ValidationError(str(error)) from error
        expected = canonical_policy_hash(
            schema_version=self.schema_version,
            version=self.version,
            quota_limits=quota_limits,
            retention_days=retention_days,
        )
        if self.policy_sha256 and self.policy_sha256 != expected:
            raise ValidationError("operational policy hash does not match its content")
        self.policy_sha256 = expected

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("operational policies are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("operational policies are immutable")


class UsageCounter(models.Model):
    """Authoritative fixed-window usage; Redis may cache but never replace this row."""

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="usage_counters"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="releaseproof_usage_counters",
        null=True,
        blank=True,
    )
    scope = models.CharField(max_length=16)
    subject_key = models.CharField(max_length=128)
    quota_kind = models.CharField(max_length=64)
    window_started_at = models.DateTimeField()
    window_ends_at = models.DateTimeField()
    limit = models.PositiveBigIntegerField()
    consumed = models.PositiveBigIntegerField(default=0)
    policy_version = models.PositiveIntegerField()
    policy_sha256 = models.CharField(max_length=64)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager["UsageCounter"]()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"), name="organizations_usage_counter_org_id_unique"
            ),
            models.UniqueConstraint(
                fields=(
                    "organization",
                    "scope",
                    "subject_key",
                    "quota_kind",
                    "window_started_at",
                ),
                name="organizations_usage_window_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(consumed__lte=models.F("limit")),
                name="organizations_usage_within_limit",
            ),
        ]


class UsageReservation(models.Model):
    """Append-only proof that one idempotent operation consumed a quota."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="usage_reservations"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="releaseproof_usage_reservations",
        null=True,
        blank=True,
    )
    counter = models.ForeignKey(UsageCounter, on_delete=models.PROTECT, related_name="reservations")
    scope = models.CharField(max_length=16)
    subject_key = models.CharField(max_length=128)
    quota_kind = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=160)
    quantity = models.PositiveBigIntegerField()
    correlation_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager["UsageReservation"]()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="organizations_usage_reservation_org_id_unique",
            ),
            models.UniqueConstraint(
                fields=("organization", "scope", "quota_kind", "idempotency_key"),
                name="organizations_usage_reservation_unique",
            ),
        ]

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("usage reservations are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("usage reservations are immutable")


class RetentionDeletionPlan(models.Model):
    """Immutable exact candidate set; execution requires a distinct non-dry-run plan."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="retention_deletion_plans"
    )
    policy = models.ForeignKey(
        OperationalPolicy, on_delete=models.PROTECT, related_name="retention_deletion_plans"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="releaseproof_retention_plans",
    )
    dry_run = models.BooleanField(default=True)
    cutoff_by_class = models.JSONField()
    candidate_public_ids = models.JSONField(validators=[validate_retention_candidates])
    plan_sha256 = models.CharField(max_length=64)
    correlation_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager["RetentionDeletionPlan"]()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="organizations_retention_plan_org_id_unique",
            ),
            models.UniqueConstraint(
                fields=("organization", "plan_sha256"),
                name="organizations_retention_plan_org_hash_unique",
            ),
        ]

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("retention deletion plans are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("retention deletion plans are immutable")


class RetentionDeletionGrant(models.Model):
    """Short-lived internal database grant used only within one deletion transaction."""

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="retention_deletion_grants"
    )
    plan = models.OneToOneField(
        RetentionDeletionPlan, on_delete=models.PROTECT, related_name="deletion_grant"
    )
    active = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    objects = models.Manager["RetentionDeletionGrant"]()


class RetentionDeletionExecution(models.Model):
    """Append-only deletion outcome; object identifiers remain only in the hashed plan."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="retention_deletion_executions"
    )
    plan = models.OneToOneField(
        RetentionDeletionPlan, on_delete=models.PROTECT, related_name="execution"
    )
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="releaseproof_retention_executions",
    )
    deleted_counts = models.JSONField(default=dict)
    blocked_counts = models.JSONField(default=dict)
    result_sha256 = models.CharField(max_length=64)
    correlation_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager["RetentionDeletionExecution"]()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="organizations_retention_execution_org_id_unique",
            )
        ]

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("retention deletion executions are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("retention deletion executions are immutable")


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
