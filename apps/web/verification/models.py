"""Immutable generated-test revisions and append-only human lifecycle events."""

from __future__ import annotations

import json
import uuid
from typing import Any, NoReturn

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.web.changes.models import (
    ImmutableQuerySet,
    PullRequestSnapshot,
    validate_checksum,
    validate_sha,
)
from apps.web.evidence.models import EvidenceItem, EvidenceKind
from apps.web.organizations.models import Organization
from packages.ai_core import (
    TEST_PROPOSAL_SCHEMA_VERSION,
    GeneratedTestProposalV1,
    ProposalGenerationMetadata,
    ProposalRisk,
)
from packages.execution_contracts import (
    DIFFERENTIAL_PLAN_SCHEMA_VERSION,
    DIFFERENTIAL_RESULT_SCHEMA_VERSION,
    EXECUTION_PLAN_SCHEMA_VERSION,
    EXECUTION_RESULT_SCHEMA_VERSION,
    DifferentialOutcome,
    ExecutionContractError,
    ExecutionOutcome,
    parse_differential_plan_json,
    parse_differential_result_json,
    parse_execution_plan_json,
    parse_execution_result_json,
)
from packages.recommendation_core import (
    RECOMMENDATION_POLICY_VERSION,
    Recommendation,
    fuse_recommendation,
    recommendation_decision_from_dict,
    recommendation_inputs_from_dict,
)


class ProposalLifecycle(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACCEPTED_FOR_EXPORT = "accepted_for_export", "Accepted for export"
    REJECTED = "rejected", "Rejected"
    SUPERSEDED = "superseded", "Superseded"


def validate_proposal_evidence_ids(value: Any) -> None:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > 50
        or len(set(value)) != len(value)
        or not all(
            isinstance(item, str)
            and 1 <= len(item) <= 160
            and item.isascii()
            and all(ord(character) >= 32 for character in item)
            for item in value
        )
    ):
        raise ValidationError("proposal evidence IDs must be bounded unique ASCII identifiers")


def validate_proposal_commands(value: Any) -> None:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > 5
        or len(set(value)) != len(value)
        or not all(
            isinstance(item, str) and 1 <= len(item.encode("utf-8")) <= 500 and "\x00" not in item
            for item in value
        )
    ):
        raise ValidationError("proposal commands must be bounded unique strings")


def validate_generation_metadata(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValidationError("proposal generation metadata must be an object")
    try:
        ProposalGenerationMetadata(**value)
    except (TypeError, ValueError) as error:
        raise ValidationError("proposal generation metadata is invalid") from error


def validate_static_validation_report(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {
        "validator_version",
        "valid",
        "content_sha256",
        "checks",
    }:
        raise ValidationError("proposal validation report has an invalid shape")
    if (
        not isinstance(value["validator_version"], str)
        or len(value["validator_version"]) > 64
        or not isinstance(value["valid"], bool)
    ):
        raise ValidationError("proposal validation report identity is invalid")
    content_hash = value["content_sha256"]
    if content_hash is not None:
        try:
            validate_checksum(content_hash)
        except ValidationError as error:
            raise ValidationError("proposal validation content hash is invalid") from error
    checks = value["checks"]
    if not isinstance(checks, list) or not 1 <= len(checks) <= 12:
        raise ValidationError("proposal validation checks are invalid")
    for check in checks:
        if (
            not isinstance(check, dict)
            or set(check) != {"name", "passed", "code"}
            or not isinstance(check["name"], str)
            or not 1 <= len(check["name"]) <= 64
            or not isinstance(check["passed"], bool)
            or not isinstance(check["code"], str)
            or not 1 <= len(check["code"]) <= 128
        ):
            raise ValidationError("proposal validation check is invalid")


class GeneratedTestProposalQuerySet(ImmutableQuerySet["GeneratedTestProposal"]):
    def for_organization(
        self,
        organization: Organization | int,
    ) -> GeneratedTestProposalQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class GeneratedTestProposal(models.Model):
    """One immutable content revision; lifecycle lives in append-only events."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="generated_test_proposals",
    )
    source_llm_evidence = models.ForeignKey(
        EvidenceItem,
        on_delete=models.PROTECT,
        related_name="generated_test_proposals",
    )
    proposal_group_id = models.UUIDField(default=uuid.uuid4)
    revision = models.PositiveIntegerField()
    parent_proposal = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="revisions",
        null=True,
        blank=True,
    )
    schema_version = models.CharField(max_length=64, default=TEST_PROPOSAL_SCHEMA_VERSION)
    proposal_hash = models.CharField(max_length=64, validators=[validate_checksum])
    target_behavior = models.CharField(max_length=500)
    rationale = models.TextField(max_length=2_000)
    evidence_ids = models.JSONField(validators=[validate_proposal_evidence_ids])
    file_path = models.CharField(max_length=240)
    patch = models.TextField(max_length=65_536)
    commands = models.JSONField(validators=[validate_proposal_commands])
    expected_result = models.TextField(max_length=1_000)
    risk = models.CharField(
        max_length=16, choices=[(item.value, item.value) for item in ProposalRisk]
    )
    test_adapter = models.CharField(max_length=64)
    test_adapter_version = models.CharField(max_length=64)
    generation_metadata = models.JSONField(validators=[validate_generation_metadata])
    validation_report = models.JSONField(validators=[validate_static_validation_report])
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="generated_test_proposals",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = GeneratedTestProposalQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="verification_proposal_org_id_unique",
            ),
            models.UniqueConstraint(
                fields=("proposal_group_id", "revision"),
                name="verification_proposal_group_revision_unique",
            ),
            models.UniqueConstraint(
                fields=("source_llm_evidence", "proposal_hash"),
                name="verification_proposal_source_hash_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(schema_version=TEST_PROPOSAL_SCHEMA_VERSION),
                name="verification_proposal_schema_v1",
            ),
            models.CheckConstraint(
                condition=models.Q(risk__in=[item.value for item in ProposalRisk]),
                name="verification_proposal_risk_allowed",
            ),
        ]
        ordering = ("-created_at", "-id")

    def as_contract(self) -> GeneratedTestProposalV1:
        return GeneratedTestProposalV1(
            schema_version=self.schema_version,
            target_behavior=self.target_behavior,
            rationale=self.rationale,
            evidence_ids=tuple(str(value) for value in self.evidence_ids),
            file_path=self.file_path,
            patch=self.patch,
            commands=tuple(str(value) for value in self.commands),
            expected_result=self.expected_result,
            risk=ProposalRisk(self.risk),
            test_adapter=self.test_adapter,
            test_adapter_version=self.test_adapter_version,
            generation=ProposalGenerationMetadata(**self.generation_metadata),
        )

    def clean(self) -> None:
        super().clean()
        if self.organization_id is None or self.source_llm_evidence_id is None:
            return
        if self.source_llm_evidence.organization_id != self.organization_id:
            raise ValidationError("proposal and source evidence must share an organization")
        if self.source_llm_evidence.kind != EvidenceKind.LLM:
            raise ValidationError("proposal source evidence must be LLM evidence")
        if self.parent_proposal_id is not None:
            parent = self.parent_proposal
            if (
                parent is None
                or parent.organization_id != self.organization_id
                or parent.proposal_group_id != self.proposal_group_id
                or self.revision != parent.revision + 1
            ):
                raise ValidationError("proposal parent must be the prior same-tenant revision")
        elif self.revision != 1:
            raise ValidationError("an initial proposal must be revision one")
        try:
            contract = self.as_contract()
        except (TypeError, ValueError) as error:
            raise ValidationError("proposal contract is invalid") from error
        if contract.proposal_sha256 != self.proposal_hash:
            raise ValidationError("proposal hash does not match its immutable content")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("generated test proposals are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("generated test proposals are immutable")


class ProposalLifecycleEventQuerySet(ImmutableQuerySet["ProposalLifecycleEvent"]):
    def for_organization(
        self,
        organization: Organization | int,
    ) -> ProposalLifecycleEventQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class ProposalLifecycleEvent(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="proposal_lifecycle_events",
    )
    proposal = models.ForeignKey(
        GeneratedTestProposal,
        on_delete=models.PROTECT,
        related_name="lifecycle_events",
    )
    sequence = models.PositiveSmallIntegerField()
    from_lifecycle = models.CharField(
        max_length=32,
        choices=ProposalLifecycle,
        null=True,
        blank=True,
    )
    to_lifecycle = models.CharField(max_length=32, choices=ProposalLifecycle)
    reason_code = models.CharField(max_length=128)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="proposal_lifecycle_events",
        null=True,
        blank=True,
    )
    correlation_id = models.UUIDField()
    occurred_at = models.DateTimeField(auto_now_add=True)

    objects = ProposalLifecycleEventQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="verification_event_org_id_unique",
            ),
            models.UniqueConstraint(
                fields=("proposal", "sequence"),
                name="verification_event_proposal_sequence_unique",
            ),
            models.UniqueConstraint(
                fields=("proposal", "to_lifecycle"),
                name="verification_event_proposal_lifecycle_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(to_lifecycle__in=[item.value for item in ProposalLifecycle]),
                name="verification_event_to_lifecycle_allowed",
            ),
            models.CheckConstraint(
                condition=models.Q(from_lifecycle__isnull=True)
                | models.Q(from_lifecycle__in=[item.value for item in ProposalLifecycle]),
                name="verification_event_from_lifecycle_allowed",
            ),
        ]
        ordering = ("proposal_id", "sequence", "id")

    def clean(self) -> None:
        super().clean()
        if self.organization_id is None or self.proposal_id is None:
            return
        if self.proposal.organization_id != self.organization_id:
            raise ValidationError("proposal event and proposal must share an organization")
        if self.sequence == 0:
            if self.from_lifecycle is not None or self.to_lifecycle != ProposalLifecycle.DRAFT:
                raise ValidationError("the first proposal event must create a draft")
        elif self.from_lifecycle is None:
            raise ValidationError("later proposal events require a prior lifecycle")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("proposal lifecycle events are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("proposal lifecycle events are immutable")


def validate_execution_plan_payload(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValidationError("execution plan payload must be an object")
    try:
        parse_execution_plan_json(
            json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)
        )
    except (ExecutionContractError, TypeError, ValueError) as error:
        raise ValidationError("execution plan payload is invalid") from error


def validate_execution_result_payload(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValidationError("execution result payload must be an object")
    try:
        parse_execution_result_json(
            json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)
        )
    except (ExecutionContractError, TypeError, ValueError) as error:
        raise ValidationError("execution result payload is invalid") from error


class ExecutionPlanQuerySet(ImmutableQuerySet["ExecutionPlan"]):
    def for_organization(self, organization: Organization | int) -> ExecutionPlanQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class ExecutionPlan(models.Model):
    """One immutable execution authorization target; it never starts execution itself."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="execution_plans"
    )
    proposal = models.ForeignKey(
        GeneratedTestProposal, on_delete=models.PROTECT, related_name="execution_plans"
    )
    snapshot = models.ForeignKey(
        PullRequestSnapshot, on_delete=models.PROTECT, related_name="execution_plans"
    )
    schema_version = models.CharField(max_length=64, default=EXECUTION_PLAN_SCHEMA_VERSION)
    plan_hash = models.CharField(max_length=64, validators=[validate_checksum])
    proposal_hash = models.CharField(max_length=64, validators=[validate_checksum])
    snapshot_head_sha = models.CharField(max_length=64, validators=[validate_sha])
    image = models.CharField(max_length=160)
    fixture_tree_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    payload = models.JSONField(validators=[validate_execution_plan_payload])
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="execution_plans_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ExecutionPlanQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"), name="verification_plan_org_id_unique"
            ),
            models.UniqueConstraint(
                fields=("organization", "plan_hash"), name="verification_plan_org_hash_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(schema_version=EXECUTION_PLAN_SCHEMA_VERSION),
                name="verification_execution_plan_schema_v1",
            ),
        ]
        ordering = ("-created_at", "-id")

    def clean(self) -> None:
        super().clean()
        if self.organization_id is None or self.proposal_id is None or self.snapshot_id is None:
            return
        plan = parse_execution_plan_json(json.dumps(self.payload, sort_keys=True))
        if (
            self.proposal.organization_id != self.organization_id
            or self.snapshot.organization_id != self.organization_id
            or self.proposal.source_llm_evidence.snapshot_id != self.snapshot_id
        ):
            raise ValidationError(
                "execution plan relationships must share the exact tenant snapshot"
            )
        if (
            plan.plan_sha256 != self.plan_hash
            or plan.proposal_hash != self.proposal_hash
            or plan.checkout_sha != self.snapshot_head_sha
            or plan.image != self.image
            or plan.fixture_tree_sha256 != self.fixture_tree_sha256
        ):
            raise ValidationError("execution plan columns do not match its payload")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("execution plans are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("execution plans are immutable")


class ExecutionApproval(models.Model):
    """Append-only human approval bound to the exact M9 plan inputs."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="execution_approvals"
    )
    plan = models.OneToOneField(ExecutionPlan, on_delete=models.PROTECT, related_name="approval")
    snapshot_head_sha = models.CharField(max_length=64, validators=[validate_sha])
    proposal_hash = models.CharField(max_length=64, validators=[validate_checksum])
    plan_hash = models.CharField(max_length=64, validators=[validate_checksum])
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="execution_approvals"
    )
    correlation_id = models.UUIDField()
    occurred_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager["ExecutionApproval"]()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"), name="verification_approval_org_id_unique"
            ),
        ]
        ordering = ("-occurred_at", "-id")

    def clean(self) -> None:
        super().clean()
        if self.organization_id is None or self.plan_id is None:
            return
        if (
            self.plan.organization_id != self.organization_id
            or self.snapshot_head_sha != self.plan.snapshot_head_sha
            or self.proposal_hash != self.plan.proposal_hash
            or self.plan_hash != self.plan.plan_hash
        ):
            raise ValidationError("execution approval must bind the exact tenant plan")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("execution approvals are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("execution approvals are immutable")


class ExecutionRun(models.Model):
    """Append-only, idempotent safe result evidence returned by the runner."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="execution_runs"
    )
    plan = models.ForeignKey(ExecutionPlan, on_delete=models.PROTECT, related_name="runs")
    approval = models.ForeignKey(ExecutionApproval, on_delete=models.PROTECT, related_name="runs")
    schema_version = models.CharField(max_length=64, default=EXECUTION_RESULT_SCHEMA_VERSION)
    result_hash = models.CharField(max_length=64, validators=[validate_checksum])
    attempt = models.PositiveSmallIntegerField()
    outcome = models.CharField(
        max_length=32, choices=[(item.value, item.value) for item in ExecutionOutcome]
    )
    idempotency_key = models.UUIDField()
    stale_at_recording = models.BooleanField(default=False)
    payload = models.JSONField(validators=[validate_execution_result_payload])
    recorded_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager["ExecutionRun"]()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"), name="verification_run_org_id_unique"
            ),
            models.UniqueConstraint(
                fields=("organization", "idempotency_key"), name="verification_run_org_idempotent"
            ),
            models.UniqueConstraint(
                fields=("plan", "attempt"), name="verification_run_plan_attempt_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(schema_version=EXECUTION_RESULT_SCHEMA_VERSION),
                name="verification_execution_result_schema_v1",
            ),
            models.CheckConstraint(
                condition=models.Q(outcome__in=[item.value for item in ExecutionOutcome]),
                name="verification_execution_outcome_allowed",
            ),
        ]
        ordering = ("plan_id", "attempt", "id")

    def clean(self) -> None:
        super().clean()
        if self.organization_id is None or self.plan_id is None or self.approval_id is None:
            return
        result = parse_execution_result_json(json.dumps(self.payload, sort_keys=True))
        if (
            self.plan.organization_id != self.organization_id
            or self.approval.organization_id != self.organization_id
            or self.approval.plan_id != self.plan_id
            or result.plan_sha256 != self.plan.plan_hash
            or result.result_sha256 != self.result_hash
            or result.attempt != self.attempt
            or result.outcome.value != self.outcome
        ):
            raise ValidationError("execution result must bind the exact approved tenant plan")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("execution runs are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("execution runs are immutable")


def validate_differential_plan_payload(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValidationError("differential plan payload must be an object")
    try:
        parse_differential_plan_json(json.dumps(value, sort_keys=True))
    except (ExecutionContractError, TypeError, ValueError) as error:
        raise ValidationError("differential plan payload is invalid") from error


def validate_differential_result_payload(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValidationError("differential result payload must be an object")
    try:
        parse_differential_result_json(json.dumps(value, sort_keys=True))
    except (ExecutionContractError, TypeError, ValueError) as error:
        raise ValidationError("differential result payload is invalid") from error


def validate_recommendation_payload(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"decision", "inputs"}:
        raise ValidationError("recommendation payload is invalid")
    try:
        inputs = recommendation_inputs_from_dict(value["inputs"])
        decision = recommendation_decision_from_dict(value["decision"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValidationError("recommendation payload is invalid") from error
    if fuse_recommendation(inputs) != decision:
        raise ValidationError("recommendation payload does not match the deterministic policy")


class DifferentialPlanQuerySet(ImmutableQuerySet["DifferentialPlan"]):
    def for_organization(self, organization: Organization | int) -> DifferentialPlanQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class DifferentialPlan(models.Model):
    """One immutable M10 plan chained to an exact separately approved M9 plan."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="differential_plans"
    )
    source_execution_plan = models.OneToOneField(
        ExecutionPlan, on_delete=models.PROTECT, related_name="differential_plan"
    )
    source_approval = models.ForeignKey(
        ExecutionApproval, on_delete=models.PROTECT, related_name="differential_plans"
    )
    schema_version = models.CharField(max_length=64, default=DIFFERENTIAL_PLAN_SCHEMA_VERSION)
    plan_hash = models.CharField(max_length=64, validators=[validate_checksum])
    base_sha = models.CharField(max_length=40, validators=[validate_sha])
    candidate_sha = models.CharField(max_length=40, validators=[validate_sha])
    image = models.CharField(max_length=160)
    payload = models.JSONField(validators=[validate_differential_plan_payload])
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="differential_plans_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = DifferentialPlanQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"), name="verification_diff_plan_org_id_unique"
            ),
            models.UniqueConstraint(
                fields=("organization", "plan_hash"),
                name="verification_diff_plan_org_hash_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(schema_version=DIFFERENTIAL_PLAN_SCHEMA_VERSION),
                name="verification_diff_plan_schema_v1",
            ),
        ]
        ordering = ("-created_at", "-id")

    def clean(self) -> None:
        super().clean()
        if self.organization_id is None or self.source_execution_plan_id is None:
            return
        plan = parse_differential_plan_json(json.dumps(self.payload, sort_keys=True))
        source = self.source_execution_plan
        approval = self.source_approval
        if (
            source.organization_id != self.organization_id
            or approval.organization_id != self.organization_id
            or approval.plan_id != source.id
            or plan.execution_plan_id != str(source.public_id)
            or plan.execution_approval_id != str(approval.public_id)
            or plan.execution_plan_sha256 != source.plan_hash
            or plan.snapshot_id != str(source.snapshot.public_id)
            or plan.organization_id != str(self.organization.public_id)
            or plan.repository_id != str(source.snapshot.repository.public_id)
            or plan.proposal_hash != source.proposal_hash
            or plan.plan_sha256 != self.plan_hash
            or plan.base_sha != self.base_sha
            or plan.candidate_sha != self.candidate_sha
            or plan.image != self.image
        ):
            raise ValidationError("differential plan must bind the exact approved tenant plan")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("differential plans are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("differential plans are immutable")


class DifferentialRun(models.Model):
    """Append-only comparable base/candidate and bounded mutation evidence."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="differential_runs"
    )
    plan = models.ForeignKey(DifferentialPlan, on_delete=models.PROTECT, related_name="runs")
    schema_version = models.CharField(max_length=64, default=DIFFERENTIAL_RESULT_SCHEMA_VERSION)
    result_hash = models.CharField(max_length=64, validators=[validate_checksum])
    attempt = models.PositiveSmallIntegerField()
    outcome = models.CharField(
        max_length=32, choices=[(item.value, item.value) for item in DifferentialOutcome]
    )
    mutation_killed = models.PositiveSmallIntegerField()
    mutation_total = models.PositiveSmallIntegerField()
    idempotency_key = models.UUIDField()
    stale_at_recording = models.BooleanField(default=False)
    payload = models.JSONField(validators=[validate_differential_result_payload])
    recorded_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager["DifferentialRun"]()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"), name="verification_diff_run_org_id_unique"
            ),
            models.UniqueConstraint(
                fields=("organization", "idempotency_key"),
                name="verification_diff_run_org_idempotent",
            ),
            models.UniqueConstraint(
                fields=("plan", "attempt"), name="verification_diff_run_plan_attempt_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(schema_version=DIFFERENTIAL_RESULT_SCHEMA_VERSION),
                name="verification_diff_result_schema_v1",
            ),
            models.CheckConstraint(
                condition=models.Q(outcome__in=[item.value for item in DifferentialOutcome]),
                name="verification_diff_outcome_allowed",
            ),
            models.CheckConstraint(
                condition=models.Q(mutation_killed__lte=models.F("mutation_total")),
                name="verification_mutation_killed_lte_total",
            ),
        ]
        ordering = ("plan_id", "attempt", "id")

    def clean(self) -> None:
        super().clean()
        if self.organization_id is None or self.plan_id is None:
            return
        result = parse_differential_result_json(json.dumps(self.payload, sort_keys=True))
        if (
            self.plan.organization_id != self.organization_id
            or result.plan_sha256 != self.plan.plan_hash
            or result.result_sha256 != self.result_hash
            or result.attempt != self.attempt
            or result.outcome.value != self.outcome
            or result.mutation_killed != self.mutation_killed
            or result.mutation_total != self.mutation_total
        ):
            raise ValidationError("differential result must bind the exact tenant plan")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("differential runs are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("differential runs are immutable")


class RecommendationDecision(models.Model):
    """An immutable decision under one exact historical policy version."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="recommendation_decisions"
    )
    snapshot = models.ForeignKey(
        PullRequestSnapshot, on_delete=models.PROTECT, related_name="recommendation_decisions"
    )
    differential_run = models.ForeignKey(
        DifferentialRun, on_delete=models.PROTECT, related_name="recommendation_decisions"
    )
    policy_version = models.CharField(max_length=64, default=RECOMMENDATION_POLICY_VERSION)
    recommendation = models.CharField(
        max_length=16, choices=[(item.value, item.value) for item in Recommendation]
    )
    inputs_hash = models.CharField(max_length=64, validators=[validate_checksum])
    decision_hash = models.CharField(max_length=64, validators=[validate_checksum])
    payload = models.JSONField(validators=[validate_recommendation_payload])
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recommendation_decisions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager["RecommendationDecision"]()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"), name="verification_rec_org_id_unique"
            ),
            models.UniqueConstraint(
                fields=("differential_run", "policy_version"),
                name="verification_rec_run_policy_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(policy_version=RECOMMENDATION_POLICY_VERSION),
                name="verification_rec_policy_v1",
            ),
            models.CheckConstraint(
                condition=models.Q(recommendation__in=[item.value for item in Recommendation]),
                name="verification_rec_value_allowed",
            ),
        ]
        ordering = ("-created_at", "-id")

    def clean(self) -> None:
        super().clean()
        if self.organization_id is None or self.differential_run_id is None:
            return
        inputs = recommendation_inputs_from_dict(self.payload["inputs"])
        decision = recommendation_decision_from_dict(self.payload["decision"])
        if (
            self.differential_run.organization_id != self.organization_id
            or self.differential_run.plan.source_execution_plan.snapshot_id != self.snapshot_id
            or self.snapshot.organization_id != self.organization_id
            or decision != fuse_recommendation(inputs)
            or decision.policy_version != self.policy_version
            or decision.recommendation.value != self.recommendation
            or decision.inputs_sha256 != self.inputs_hash
            or decision.decision_sha256 != self.decision_hash
        ):
            raise ValidationError("recommendation decision binding is invalid")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("recommendation decisions are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("recommendation decisions are immutable")
