"""PostgreSQL-authoritative quotas and governed tenant retention workflows."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlparse

from django.contrib.auth.models import AbstractBaseUser
from django.db import DatabaseError, connection, transaction
from django.db.models.deletion import Collector, ProtectedError
from django.utils import timezone

from apps.web.audit.services import record_audit
from apps.web.organizations.models import (
    Membership,
    MembershipLifecycle,
    MembershipRole,
    OperationalPolicy,
    Organization,
    RetentionDeletionExecution,
    RetentionDeletionGrant,
    RetentionDeletionPlan,
    UsageCounter,
    UsageReservation,
)
from packages.observability import (
    DEFAULT_QUOTA_LIMITS,
    DEFAULT_RETENTION_DAYS,
    OPERATIONAL_POLICY_SCHEMA_VERSION,
    QuotaKind,
    QuotaScope,
    RetentionClass,
    canonical_policy_hash,
    current_correlation_id,
    validate_quota_limits,
    validate_retention_days,
)

MAX_RETENTION_CANDIDATES = 1_000
RETENTION_PLAN_TTL = timedelta(days=7)


class QuotaExceededError(RuntimeError):
    def __init__(self, *, kind: QuotaKind, scope: QuotaScope, retry_after_seconds: int) -> None:
        super().__init__(f"{kind.value} quota exceeded")
        self.kind = kind
        self.scope = scope
        self.retry_after_seconds = max(1, retry_after_seconds)


class OperationalPolicyError(ValueError):
    pass


class RetentionWorkflowError(ValueError):
    pass


class ArtifactPurger(Protocol):
    def purge(self, *, uri: str, sha256: str) -> None: ...


class S3ArtifactPurger:
    """Delete only checksum-matched objects in the configured authoritative bucket."""

    def __init__(self) -> None:
        from adapters.object_storage.s3 import S3ObjectStorage, S3Settings

        settings = S3Settings.from_environment()
        self._bucket = settings.bucket
        self._storage = S3ObjectStorage(settings)

    def purge(self, *, uri: str, sha256: str) -> None:
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or parsed.netloc != self._bucket:
            raise ValueError("only the configured S3 bucket can be purged")
        key = parsed.path.lstrip("/")
        metadata = self._storage.head(key)
        if metadata.sha256 != sha256:
            raise ValueError("artifact checksum differs from authoritative storage metadata")
        self._storage.delete(key)


@dataclass(frozen=True, slots=True)
class EffectiveOperationalPolicy:
    version: int
    schema_version: str
    quota_limits: Mapping[str, int]
    retention_days: Mapping[str, int]
    policy_sha256: str
    record: OperationalPolicy | None


@dataclass(frozen=True, slots=True)
class QuotaReservationResult:
    reservations: tuple[UsageReservation, ...]
    duplicate: bool


@dataclass(frozen=True, slots=True)
class QuotaBundleItem:
    kind: QuotaKind
    quantity: int


@dataclass(frozen=True, slots=True)
class RetentionExecutionResult:
    execution: RetentionDeletionExecution
    created: bool


def _canonical_hash(value: object) -> str:
    canonical = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(canonical).hexdigest()


def _membership_role(*, organization: Organization, actor: AbstractBaseUser) -> MembershipRole:
    membership = (
        Membership.objects.active()
        .filter(
            organization=organization,
            user_id=actor.pk,
            lifecycle=MembershipLifecycle.ACTIVE,
        )
        .first()
    )
    if membership is None or membership.role not in {MembershipRole.OWNER, MembershipRole.ADMIN}:
        raise OperationalPolicyError("owner_or_admin_required")
    return MembershipRole(membership.role)


def resolve_operational_policy(*, organization: Organization) -> EffectiveOperationalPolicy:
    record = OperationalPolicy.objects.for_organization(organization).order_by("-version").first()
    if record is None:
        quota_limits = dict(DEFAULT_QUOTA_LIMITS)
        retention_days = dict(DEFAULT_RETENTION_DAYS)
        return EffectiveOperationalPolicy(
            version=0,
            schema_version=OPERATIONAL_POLICY_SCHEMA_VERSION,
            quota_limits=quota_limits,
            retention_days=retention_days,
            policy_sha256=canonical_policy_hash(
                schema_version=OPERATIONAL_POLICY_SCHEMA_VERSION,
                version=0,
                quota_limits=quota_limits,
                retention_days=retention_days,
            ),
            record=None,
        )
    return EffectiveOperationalPolicy(
        version=record.version,
        schema_version=record.schema_version,
        quota_limits=validate_quota_limits(record.quota_limits),
        retention_days=validate_retention_days(record.retention_days),
        policy_sha256=record.policy_sha256,
        record=record,
    )


@transaction.atomic
def create_operational_policy(
    *,
    organization: Organization,
    actor: AbstractBaseUser,
    quota_limits: Mapping[str, int],
    retention_days: Mapping[str, int],
) -> OperationalPolicy:
    role = _membership_role(organization=organization, actor=actor)
    locked = Organization.objects.select_for_update().get(pk=organization.pk)
    version = (
        OperationalPolicy.objects.for_organization(locked)
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    ) + 1
    normalized_quota_limits = validate_quota_limits(dict(quota_limits))
    normalized_retention_days = validate_retention_days(dict(retention_days))
    policy = OperationalPolicy(
        organization=locked,
        version=version,
        quota_limits=normalized_quota_limits,
        retention_days=normalized_retention_days,
        policy_sha256=canonical_policy_hash(
            schema_version=OPERATIONAL_POLICY_SCHEMA_VERSION,
            version=version,
            quota_limits=normalized_quota_limits,
            retention_days=normalized_retention_days,
        ),
        approved_by_role=role.value,
        created_by_id=actor.pk,
    )
    policy.full_clean()
    policy.save()
    correlation_id = current_correlation_id()
    record_audit(
        organization=locked,
        actor=actor,
        action="operational_policy.created",
        resource_type="operational_policy",
        resource_public_id=policy.public_id,
        correlation_id=correlation_id,
        metadata={
            "policy_hash": policy.policy_sha256,
            "policy_version": policy.version,
            "role": role.value,
        },
    )
    return policy


def _window(*, kind: QuotaKind, now: datetime) -> tuple[datetime, datetime]:
    seconds = 60 if kind.value.endswith("per_minute") else 3_600
    if kind.value.endswith("per_day"):
        seconds = 86_400
    epoch_seconds = int(now.timestamp())
    start = datetime.fromtimestamp(epoch_seconds - (epoch_seconds % seconds), tz=UTC)
    return start, start + timedelta(seconds=seconds)


def validate_upload_size(*, organization: Organization, byte_count: int) -> None:
    if isinstance(byte_count, bool) or byte_count < 0:
        raise ValueError("upload byte count must be a non-negative integer")
    policy = resolve_operational_policy(organization=organization)
    limit = policy.quota_limits[QuotaKind.UPLOAD_BYTES_PER_REQUEST.value]
    if byte_count > limit:
        raise QuotaExceededError(
            kind=QuotaKind.UPLOAD_BYTES_PER_REQUEST,
            scope=QuotaScope.TENANT,
            retry_after_seconds=1,
        )


@transaction.atomic
def reserve_quota(
    *,
    organization: Organization,
    kind: QuotaKind,
    quantity: int,
    idempotency_key: str,
    actor: AbstractBaseUser | None = None,
    correlation_id: uuid.UUID | None = None,
) -> QuotaReservationResult:
    if kind is QuotaKind.UPLOAD_BYTES_PER_REQUEST:
        validate_upload_size(organization=organization, byte_count=quantity)
        return QuotaReservationResult((), False)
    if isinstance(quantity, bool) or quantity < 1:
        raise ValueError("quota quantity must be a positive integer")
    if not idempotency_key.isascii() or not 1 <= len(idempotency_key) <= 160:
        raise ValueError("quota idempotency key must be bounded ASCII")
    locked_org = Organization.objects.select_for_update().get(pk=organization.pk)
    policy = resolve_operational_policy(organization=locked_org)
    limit = policy.quota_limits[kind.value]
    now = timezone.now()
    window_start, window_end = _window(kind=kind, now=now)
    resolved_correlation = correlation_id or current_correlation_id()
    subjects: list[tuple[QuotaScope, str, int | None]] = [
        (QuotaScope.TENANT, f"tenant:{locked_org.public_id}", None)
    ]
    if actor is not None:
        if actor.pk is None:
            raise ValueError("quota actor must be persisted")
        subjects.append((QuotaScope.USER, f"user:{actor.pk}", int(actor.pk)))

    existing: list[UsageReservation] = []
    for scope, _subject_key, _actor_id in subjects:
        reservation = UsageReservation.objects.filter(
            organization=locked_org,
            scope=scope.value,
            quota_kind=kind.value,
            idempotency_key=idempotency_key,
        ).first()
        if reservation is not None:
            existing.append(reservation)
    if existing:
        if len(existing) != len(subjects) or any(item.quantity != quantity for item in existing):
            raise ValueError("quota idempotency key conflicts with a prior reservation")
        return QuotaReservationResult(tuple(existing), True)

    reservations: list[UsageReservation] = []
    for scope, subject_key, actor_id in subjects:
        counter, _created = UsageCounter.objects.get_or_create(
            organization=locked_org,
            scope=scope.value,
            subject_key=subject_key,
            quota_kind=kind.value,
            window_started_at=window_start,
            defaults={
                "actor_id": actor_id,
                "window_ends_at": window_end,
                "limit": limit,
                "policy_version": policy.version,
                "policy_sha256": policy.policy_sha256,
            },
        )
        counter = UsageCounter.objects.select_for_update().get(pk=counter.pk)
        # A fixed window remains bound to the policy that opened it.
        effective_limit = counter.limit
        if counter.consumed + quantity > effective_limit:
            raise QuotaExceededError(
                kind=kind,
                scope=scope,
                retry_after_seconds=int(max(1.0, (counter.window_ends_at - now).total_seconds())),
            )
        counter.consumed += quantity
        counter.save(update_fields=("consumed", "updated_at"))
        reservation = UsageReservation.objects.create(
            organization=locked_org,
            actor_id=actor_id,
            counter=counter,
            scope=scope.value,
            subject_key=subject_key,
            quota_kind=kind.value,
            idempotency_key=idempotency_key,
            quantity=quantity,
            correlation_id=resolved_correlation,
        )
        reservations.append(reservation)
    return QuotaReservationResult(tuple(reservations), False)


@transaction.atomic
def reserve_upload(
    *,
    organization: Organization,
    byte_count: int,
    idempotency_key: str,
    actor: AbstractBaseUser | None = None,
    correlation_id: uuid.UUID | None = None,
) -> QuotaReservationResult:
    """Apply the independent size and request-rate boundaries for an upload."""

    locked_org = Organization.objects.select_for_update().get(pk=organization.pk)
    validate_upload_size(organization=locked_org, byte_count=byte_count)
    return reserve_quota(
        organization=locked_org,
        kind=QuotaKind.UPLOAD_REQUESTS_PER_HOUR,
        quantity=1,
        idempotency_key=idempotency_key,
        actor=actor,
        correlation_id=correlation_id,
    )


@transaction.atomic
def reserve_quota_bundle(
    *,
    organization: Organization,
    items: tuple[QuotaBundleItem, ...],
    idempotency_key: str,
    actor: AbstractBaseUser | None = None,
    correlation_id: uuid.UUID | None = None,
) -> tuple[QuotaReservationResult, ...]:
    if not items or len({item.kind for item in items}) != len(items):
        raise ValueError("quota bundle must contain unique quota kinds")
    return tuple(
        reserve_quota(
            organization=organization,
            kind=item.kind,
            quantity=item.quantity,
            idempotency_key=idempotency_key,
            actor=actor,
            correlation_id=correlation_id,
        )
        for item in items
    )


def _eligible_candidates(
    *, organization: Organization, policy: OperationalPolicy, now: datetime
) -> tuple[dict[str, str], dict[str, list[str]]]:
    from apps.web.changes.models import PullRequestSnapshot
    from apps.web.evidence.models import EvidenceItem
    from apps.web.retrieval.models import KnowledgeEmbedding384
    from apps.web.risk.models import GovernedModelArtifact

    model_by_class = {
        RetentionClass.SOURCE_SNAPSHOT: PullRequestSnapshot,
        RetentionClass.EMBEDDING: KnowledgeEmbedding384,
        RetentionClass.ARTIFACT: GovernedModelArtifact,
        RetentionClass.ANALYSIS: EvidenceItem,
    }
    cutoffs: dict[str, str] = {}
    candidates: dict[str, list[str]] = {}
    remaining = MAX_RETENTION_CANDIDATES
    for retention_class, model in model_by_class.items():
        cutoff = now - timedelta(days=policy.retention_days[retention_class.value])
        cutoffs[retention_class.value] = cutoff.isoformat()
        queryset = model._base_manager.filter(organization=organization, created_at__lt=cutoff)
        if retention_class is RetentionClass.EMBEDDING:
            queryset = queryset.filter(chunk__document__retain_until__lte=now)
        public_ids = [
            str(item) for item in queryset.values_list("public_id", flat=True)[:remaining]
        ]
        candidates[retention_class.value] = public_ids
        remaining -= len(public_ids)
    return cutoffs, candidates


@transaction.atomic
def create_retention_deletion_plan(
    *, organization: Organization, actor: AbstractBaseUser, dry_run: bool = True
) -> RetentionDeletionPlan:
    role = _membership_role(organization=organization, actor=actor)
    del role
    policy = resolve_operational_policy(organization=organization)
    if policy.record is None:
        policy_record = create_operational_policy(
            organization=organization,
            actor=actor,
            quota_limits=DEFAULT_QUOTA_LIMITS,
            retention_days=DEFAULT_RETENTION_DAYS,
        )
    else:
        policy_record = policy.record
    now = timezone.now()
    cutoffs, candidates = _eligible_candidates(
        organization=organization, policy=policy_record, now=now
    )
    correlation_id = current_correlation_id()
    payload = {
        "candidate_public_ids": candidates,
        "cutoff_by_class": cutoffs,
        "dry_run": dry_run,
        "organization_id": str(organization.public_id),
        "policy_sha256": policy_record.policy_sha256,
    }
    plan = RetentionDeletionPlan(
        organization=organization,
        policy=policy_record,
        requested_by_id=actor.pk,
        dry_run=dry_run,
        cutoff_by_class=cutoffs,
        candidate_public_ids=candidates,
        plan_sha256=_canonical_hash(payload),
        correlation_id=correlation_id,
    )
    plan.full_clean()
    plan.save()
    record_audit(
        organization=organization,
        actor=actor,
        action="retention.plan_created",
        resource_type="retention_deletion_plan",
        resource_public_id=plan.public_id,
        correlation_id=correlation_id,
        metadata={
            "candidate_count": sum(len(items) for items in candidates.values()),
            "dry_run": dry_run,
            "plan_hash": plan.plan_sha256,
            "policy_version": policy_record.version,
        },
    )
    return plan


_TABLE_BY_RETENTION_CLASS = {
    RetentionClass.SOURCE_SNAPSHOT.value: "changes_pullrequestsnapshot",
    RetentionClass.EMBEDDING.value: "retrieval_knowledgeembedding384",
    RetentionClass.ARTIFACT.value: "risk_governedmodelartifact",
    RetentionClass.ANALYSIS.value: "evidence_evidenceitem",
}


def _artifact_identity(*, organization: Organization, public_id: str) -> tuple[str, str] | None:
    from apps.web.risk.models import GovernedModelArtifact

    artifact = (
        GovernedModelArtifact._base_manager.select_for_update()
        .filter(organization=organization, public_id=public_id)
        .first()
    )
    if artifact is None:
        return None
    collector = Collector(using=artifact._state.db or "default")
    collector.collect((artifact,))
    return artifact.artifact_uri, artifact.artifact_sha256


@transaction.atomic
def execute_retention_deletion_plan(
    *,
    organization: Organization,
    plan_public_id: uuid.UUID | str,
    actor: AbstractBaseUser,
    artifact_purger: ArtifactPurger | None = None,
) -> RetentionExecutionResult:
    _membership_role(organization=organization, actor=actor)
    plan = (
        RetentionDeletionPlan.objects.select_for_update()
        .filter(organization=organization, public_id=plan_public_id)
        .first()
    )
    if plan is None:
        raise RetentionWorkflowError("retention_plan_not_found")
    if plan.dry_run:
        raise RetentionWorkflowError("dry_run_plan_cannot_execute")
    if plan.created_at + RETENTION_PLAN_TTL <= timezone.now():
        raise RetentionWorkflowError("retention_plan_expired")
    existing = RetentionDeletionExecution.objects.filter(
        organization=organization, plan=plan
    ).first()
    if existing is not None:
        return RetentionExecutionResult(existing, False)
    if (
        resolve_operational_policy(organization=organization).policy_sha256
        != plan.policy.policy_sha256
    ):
        raise RetentionWorkflowError("retention_policy_changed")

    grant, _created = RetentionDeletionGrant.objects.update_or_create(
        organization=organization,
        plan=plan,
        defaults={"active": True, "expires_at": timezone.now() + timedelta(minutes=5)},
    )
    deleted = dict.fromkeys(_TABLE_BY_RETENTION_CLASS, 0)
    blocked = dict.fromkeys(_TABLE_BY_RETENTION_CLASS, 0)
    try:
        for retention_class, public_ids in plan.candidate_public_ids.items():
            table = _TABLE_BY_RETENTION_CLASS[retention_class]
            for public_id in public_ids:
                database_public_id = (
                    uuid.UUID(public_id).hex if connection.vendor == "sqlite" else public_id
                )
                if retention_class == RetentionClass.ARTIFACT.value:
                    try:
                        identity = _artifact_identity(
                            organization=organization, public_id=public_id
                        )
                    except ProtectedError:
                        blocked[retention_class] += 1
                        continue
                    if identity is None:
                        continue
                    if artifact_purger is None:
                        blocked[retention_class] += 1
                        continue
                    try:
                        artifact_purger.purge(uri=identity[0], sha256=identity[1])
                    except (OSError, RuntimeError, ValueError):
                        blocked[retention_class] += 1
                        continue
                try:
                    with transaction.atomic(), connection.cursor() as cursor:
                        cursor.execute(
                            f'DELETE FROM "{table}" WHERE "organization_id" = %s '  # noqa: S608 -- closed server map
                            'AND "public_id" = %s',
                            (organization.pk, database_public_id),
                        )
                        deleted[retention_class] += int(cursor.rowcount == 1)
                except DatabaseError:
                    blocked[retention_class] += 1
    finally:
        RetentionDeletionGrant.objects.filter(pk=grant.pk).update(active=False)
    result_payload = {
        "blocked_counts": blocked,
        "deleted_counts": deleted,
        "plan_sha256": plan.plan_sha256,
    }
    correlation_id = current_correlation_id()
    execution = RetentionDeletionExecution(
        organization=organization,
        plan=plan,
        executed_by_id=actor.pk,
        deleted_counts=deleted,
        blocked_counts=blocked,
        result_sha256=_canonical_hash(result_payload),
        correlation_id=correlation_id,
    )
    execution.full_clean()
    execution.save()
    record_audit(
        organization=organization,
        actor=actor,
        action="retention.plan_executed",
        resource_type="retention_deletion_execution",
        resource_public_id=execution.public_id,
        correlation_id=correlation_id,
        metadata={
            "blocked_count": sum(blocked.values()),
            "deleted_count": sum(deleted.values()),
            "plan_hash": plan.plan_sha256,
            "result_hash": execution.result_sha256,
        },
    )
    return RetentionExecutionResult(execution, True)
