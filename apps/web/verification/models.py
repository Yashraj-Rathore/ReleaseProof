"""Immutable generated-test revisions and append-only human lifecycle events."""

from __future__ import annotations

import uuid
from typing import Any, NoReturn

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.web.changes.models import ImmutableQuerySet, validate_checksum
from apps.web.evidence.models import EvidenceItem, EvidenceKind
from apps.web.organizations.models import Organization
from packages.ai_core import (
    TEST_PROPOSAL_SCHEMA_VERSION,
    GeneratedTestProposalV1,
    ProposalGenerationMetadata,
    ProposalRisk,
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
