"""Tenant-scoped generated-test proposal creation, review, and bounded export."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from urllib.parse import urljoin

from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.http import Http404

from adapters.test_generation import PythonFixtureTestAdapter, StaticValidationReport
from apps.web.audit.services import record_audit
from apps.web.changes.models import PullRequestSnapshot
from apps.web.evidence.models import EvidenceItem, EvidenceKind
from apps.web.organizations.models import Organization
from apps.web.verification.models import (
    GeneratedTestProposal,
    ProposalLifecycle,
    ProposalLifecycleEvent,
)
from packages.ai_core import GeneratedTestProposalV1
from packages.github_contracts import (
    AdvisoryConclusion,
    AdvisoryReport,
    GitHubAdvisoryPublisher,
    PublishedAdvisory,
)


class StaleSnapshotError(RuntimeError):
    """A historical head must not overwrite output for a newer head."""


def publish_snapshot_advisory(
    *,
    snapshot: PullRequestSnapshot,
    publisher: GitHubAdvisoryPublisher,
    dashboard_base_url: str,
) -> PublishedAdvisory:
    """Publish the established M2 neutral receipt only for the current PR head."""

    latest = (
        PullRequestSnapshot.objects.filter(
            organization=snapshot.organization,
            repository=snapshot.repository,
            pull_request_number=snapshot.pull_request_number,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if latest is None or latest.pk != snapshot.pk:
        raise StaleSnapshotError("snapshot is no longer the latest pull-request head")
    details_url = urljoin(
        dashboard_base_url.rstrip("/") + "/",
        f"app/snapshots/{snapshot.public_id}/",
    )
    report = AdvisoryReport(
        repository_id=snapshot.repository.github_repository_id,
        pull_request_number=snapshot.pull_request_number,
        head_sha=snapshot.head_sha,
        name="ReleaseProof advisory",
        conclusion=AdvisoryConclusion.NEUTRAL,
        summary=(
            "Immutable change snapshot accepted. Risk analysis is not available until its "
            "owning milestone is implemented."
        ),
        details_url=details_url,
        producer_version="m2-snapshot-receipt-v1",
    )
    return publisher.publish(report)


class ProposalWorkflowError(ValueError):
    """A safe, stable generated-test workflow rejection."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ProposalMutationResult:
    proposal: GeneratedTestProposal
    lifecycle: ProposalLifecycle
    created: bool
    correlation_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class ProposalExport:
    proposal: GeneratedTestProposal
    patch: str
    filename: str
    correlation_id: uuid.UUID


def _load_source_evidence(
    *,
    organization: Organization,
    public_id: uuid.UUID | str,
) -> EvidenceItem:
    try:
        normalized = uuid.UUID(str(public_id))
    except ValueError as error:
        raise ProposalWorkflowError("source_evidence_invalid") from error
    source = (
        EvidenceItem.objects.for_organization(organization)
        .select_related("snapshot__repository", "feature_set")
        .filter(public_id=normalized, kind=EvidenceKind.LLM)
        .first()
    )
    if source is None:
        raise ProposalWorkflowError("source_evidence_unavailable")
    return source


def _source_payload(source: EvidenceItem) -> tuple[dict[str, object], dict[str, object]]:
    if (
        source.missing
        or not isinstance(source.value, dict)
        or source.value.get("status") != "completed"
    ):
        raise ProposalWorkflowError("source_evidence_incomplete")
    provider = source.value.get("provider")
    prompt = source.value.get("prompt")
    if not isinstance(provider, dict) or not isinstance(prompt, dict):
        raise ProposalWorkflowError("source_evidence_metadata_invalid")
    return provider, prompt


def _validate_source_binding(
    *,
    source: EvidenceItem,
    proposal: GeneratedTestProposalV1,
) -> None:
    provider, prompt = _source_payload(source)
    generation = proposal.generation
    expected_source_id = f"evidence:{source.public_id}"
    if generation.source_evidence_id != expected_source_id:
        raise ProposalWorkflowError("generation_source_mismatch")
    if (
        generation.provider_name != provider.get("provider_name")
        or generation.model_id != provider.get("model_id")
        or generation.provider_adapter_version != provider.get("adapter_version")
        or generation.prompt_version != prompt.get("prompt_version")
        or generation.prompt_sha256 != prompt.get("prompt_sha256")
    ):
        raise ProposalWorkflowError("generation_metadata_mismatch")
    allowed_references = {str(value) for value in source.source_refs}
    if not set(proposal.evidence_ids).issubset(allowed_references):
        raise ProposalWorkflowError("proposal_evidence_outside_source_scope")


def _new_model(
    *,
    organization: Organization,
    source: EvidenceItem,
    proposal: GeneratedTestProposalV1,
    validation: StaticValidationReport,
    actor: AbstractBaseUser | None,
    proposal_group_id: uuid.UUID,
    revision: int,
    parent: GeneratedTestProposal | None,
) -> GeneratedTestProposal:
    return GeneratedTestProposal(
        organization=organization,
        source_llm_evidence=source,
        proposal_group_id=proposal_group_id,
        revision=revision,
        parent_proposal=parent,
        schema_version=proposal.schema_version,
        proposal_hash=proposal.proposal_sha256,
        target_behavior=proposal.target_behavior,
        rationale=proposal.rationale,
        evidence_ids=list(proposal.evidence_ids),
        file_path=proposal.file_path,
        patch=proposal.patch,
        commands=list(proposal.commands),
        expected_result=proposal.expected_result,
        risk=proposal.risk.value,
        test_adapter=proposal.test_adapter,
        test_adapter_version=proposal.test_adapter_version,
        generation_metadata=proposal.generation.as_dict(),
        validation_report=validation.as_dict(),
        created_by_id=actor.pk if actor is not None else None,
    )


def _append_event(
    *,
    proposal: GeneratedTestProposal,
    sequence: int,
    from_lifecycle: ProposalLifecycle | None,
    to_lifecycle: ProposalLifecycle,
    reason_code: str,
    actor: AbstractBaseUser | None,
    correlation_id: uuid.UUID,
) -> ProposalLifecycleEvent:
    event = ProposalLifecycleEvent(
        organization=proposal.organization,
        proposal=proposal,
        sequence=sequence,
        from_lifecycle=from_lifecycle,
        to_lifecycle=to_lifecycle,
        reason_code=reason_code,
        actor_id=actor.pk if actor is not None else None,
        correlation_id=correlation_id,
    )
    event.full_clean()
    event.save()
    return event


def _audit(
    *,
    proposal: GeneratedTestProposal,
    action: str,
    actor: AbstractBaseUser | None,
    correlation_id: uuid.UUID,
    lifecycle: ProposalLifecycle,
) -> None:
    record_audit(
        organization=proposal.organization,
        actor=actor,
        action=action,
        resource_type="generated_test_proposal",
        resource_public_id=proposal.public_id,
        correlation_id=correlation_id,
        metadata={
            "lifecycle": lifecycle.value,
            "proposal_hash": proposal.proposal_hash,
            "revision": proposal.revision,
            "validation_valid": bool(proposal.validation_report.get("valid", False)),
        },
    )


def create_test_proposal(
    *,
    organization: Organization,
    source_llm_evidence_public_id: uuid.UUID | str,
    proposal: GeneratedTestProposalV1,
    actor: AbstractBaseUser | None,
    adapter: PythonFixtureTestAdapter | None = None,
) -> ProposalMutationResult:
    source = _load_source_evidence(
        organization=organization,
        public_id=source_llm_evidence_public_id,
    )
    _validate_source_binding(source=source, proposal=proposal)
    validation = (adapter or PythonFixtureTestAdapter()).validate(proposal)
    existing = (
        GeneratedTestProposal.objects.for_organization(organization)
        .filter(source_llm_evidence=source, proposal_hash=proposal.proposal_sha256)
        .first()
    )
    if existing is not None:
        return ProposalMutationResult(
            proposal=existing,
            lifecycle=current_lifecycle(existing),
            created=False,
            correlation_id=_latest_event(existing).correlation_id,
        )
    correlation_id = uuid.uuid4()
    try:
        with transaction.atomic():
            record = _new_model(
                organization=organization,
                source=source,
                proposal=proposal,
                validation=validation,
                actor=actor,
                proposal_group_id=uuid.uuid4(),
                revision=1,
                parent=None,
            )
            record.full_clean()
            record.save()
            _append_event(
                proposal=record,
                sequence=0,
                from_lifecycle=None,
                to_lifecycle=ProposalLifecycle.DRAFT,
                reason_code="proposal_created",
                actor=actor,
                correlation_id=correlation_id,
            )
            _audit(
                proposal=record,
                action="generated_test_proposal.created",
                actor=actor,
                correlation_id=correlation_id,
                lifecycle=ProposalLifecycle.DRAFT,
            )
            return ProposalMutationResult(
                record,
                ProposalLifecycle.DRAFT,
                True,
                correlation_id,
            )
    except IntegrityError:
        existing = (
            GeneratedTestProposal.objects.for_organization(organization)
            .filter(source_llm_evidence=source, proposal_hash=proposal.proposal_sha256)
            .first()
        )
        if existing is None:
            raise
        return ProposalMutationResult(
            existing,
            current_lifecycle(existing),
            False,
            _latest_event(existing).correlation_id,
        )


def get_test_proposal(
    *,
    organization: Organization,
    public_id: uuid.UUID | str,
    lock: bool = False,
) -> GeneratedTestProposal:
    try:
        normalized = uuid.UUID(str(public_id))
    except ValueError as error:
        raise Http404("test proposal not found") from error
    queryset = GeneratedTestProposal.objects.for_organization(organization).select_related(
        "source_llm_evidence__snapshot__repository",
        "parent_proposal",
    )
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    try:
        return queryset.get(public_id=normalized)
    except GeneratedTestProposal.DoesNotExist as error:
        raise Http404("test proposal not found") from error


def _latest_event(proposal: GeneratedTestProposal) -> ProposalLifecycleEvent:
    event = proposal.lifecycle_events.order_by("-sequence", "-id").first()
    if event is None:
        raise ProposalWorkflowError("proposal_lifecycle_missing")
    return event


def current_lifecycle(proposal: GeneratedTestProposal) -> ProposalLifecycle:
    return ProposalLifecycle(_latest_event(proposal).to_lifecycle)


def transition_test_proposal(
    *,
    organization: Organization,
    proposal_public_id: uuid.UUID | str,
    target: ProposalLifecycle,
    actor: AbstractBaseUser,
) -> ProposalMutationResult:
    if target not in {ProposalLifecycle.ACCEPTED_FOR_EXPORT, ProposalLifecycle.REJECTED}:
        raise ProposalWorkflowError("transition_not_allowed_in_m8")
    with transaction.atomic():
        proposal = get_test_proposal(
            organization=organization,
            public_id=proposal_public_id,
            lock=True,
        )
        latest = _latest_event(proposal)
        current = ProposalLifecycle(latest.to_lifecycle)
        if current is target:
            return ProposalMutationResult(proposal, current, False, latest.correlation_id)
        if current is not ProposalLifecycle.DRAFT:
            raise ProposalWorkflowError("proposal_not_draft")
        if target is ProposalLifecycle.ACCEPTED_FOR_EXPORT and not bool(
            proposal.validation_report.get("valid", False)
        ):
            raise ProposalWorkflowError("invalid_proposal_cannot_be_accepted")
        correlation_id = uuid.uuid4()
        _append_event(
            proposal=proposal,
            sequence=latest.sequence + 1,
            from_lifecycle=current,
            to_lifecycle=target,
            reason_code=(
                "human_accepted_for_export"
                if target is ProposalLifecycle.ACCEPTED_FOR_EXPORT
                else "human_rejected"
            ),
            actor=actor,
            correlation_id=correlation_id,
        )
        _audit(
            proposal=proposal,
            action=f"generated_test_proposal.{target.value}",
            actor=actor,
            correlation_id=correlation_id,
            lifecycle=target,
        )
        return ProposalMutationResult(proposal, target, True, correlation_id)


def edit_test_proposal(
    *,
    organization: Organization,
    proposal_public_id: uuid.UUID | str,
    replacement: GeneratedTestProposalV1,
    actor: AbstractBaseUser,
    adapter: PythonFixtureTestAdapter | None = None,
) -> ProposalMutationResult:
    with transaction.atomic():
        previous = get_test_proposal(
            organization=organization,
            public_id=proposal_public_id,
            lock=True,
        )
        existing_child = (
            GeneratedTestProposal.objects.for_organization(organization)
            .filter(parent_proposal=previous, proposal_hash=replacement.proposal_sha256)
            .first()
        )
        if existing_child is not None:
            return ProposalMutationResult(
                existing_child,
                current_lifecycle(existing_child),
                False,
                _latest_event(existing_child).correlation_id,
            )
        latest = _latest_event(previous)
        current = ProposalLifecycle(latest.to_lifecycle)
        if current is ProposalLifecycle.SUPERSEDED:
            raise ProposalWorkflowError("proposal_already_superseded")
        old_contract = previous.as_contract()
        if replacement.proposal_sha256 == previous.proposal_hash:
            raise ProposalWorkflowError("proposal_edit_must_change_content")
        if (
            replacement.generation != old_contract.generation
            or replacement.test_adapter != old_contract.test_adapter
            or replacement.test_adapter_version != old_contract.test_adapter_version
        ):
            raise ProposalWorkflowError("proposal_edit_cannot_change_generation_identity")
        source = previous.source_llm_evidence
        _validate_source_binding(source=source, proposal=replacement)
        validation = (adapter or PythonFixtureTestAdapter()).validate(replacement)
        correlation_id = uuid.uuid4()
        revised = _new_model(
            organization=organization,
            source=source,
            proposal=replacement,
            validation=validation,
            actor=actor,
            proposal_group_id=previous.proposal_group_id,
            revision=previous.revision + 1,
            parent=previous,
        )
        revised.full_clean()
        revised.save()
        _append_event(
            proposal=revised,
            sequence=0,
            from_lifecycle=None,
            to_lifecycle=ProposalLifecycle.DRAFT,
            reason_code="human_edit_created_revision",
            actor=actor,
            correlation_id=correlation_id,
        )
        _append_event(
            proposal=previous,
            sequence=latest.sequence + 1,
            from_lifecycle=current,
            to_lifecycle=ProposalLifecycle.SUPERSEDED,
            reason_code="human_edit_superseded_revision",
            actor=actor,
            correlation_id=correlation_id,
        )
        _audit(
            proposal=previous,
            action="generated_test_proposal.superseded",
            actor=actor,
            correlation_id=correlation_id,
            lifecycle=ProposalLifecycle.SUPERSEDED,
        )
        _audit(
            proposal=revised,
            action="generated_test_proposal.revision_created",
            actor=actor,
            correlation_id=correlation_id,
            lifecycle=ProposalLifecycle.DRAFT,
        )
        return ProposalMutationResult(
            revised,
            ProposalLifecycle.DRAFT,
            True,
            correlation_id,
        )


def export_test_proposal(
    *,
    organization: Organization,
    proposal_public_id: uuid.UUID | str,
    actor: AbstractBaseUser,
) -> ProposalExport:
    with transaction.atomic():
        proposal = get_test_proposal(
            organization=organization,
            public_id=proposal_public_id,
            lock=True,
        )
        if current_lifecycle(proposal) is not ProposalLifecycle.ACCEPTED_FOR_EXPORT:
            raise ProposalWorkflowError("proposal_not_accepted_for_export")
        if not bool(proposal.validation_report.get("valid", False)):
            raise ProposalWorkflowError("invalid_proposal_cannot_be_exported")
        correlation_id = uuid.uuid4()
        _audit(
            proposal=proposal,
            action="generated_test_proposal.exported",
            actor=actor,
            correlation_id=correlation_id,
            lifecycle=ProposalLifecycle.ACCEPTED_FOR_EXPORT,
        )
        return ProposalExport(
            proposal=proposal,
            patch=proposal.patch,
            filename=f"releaseproof-proposal-{proposal.public_id}.patch",
            correlation_id=correlation_id,
        )


def serialize_test_proposal(proposal: GeneratedTestProposal) -> dict[str, object]:
    source = proposal.source_llm_evidence
    snapshot = source.snapshot
    repository = snapshot.repository
    return {
        "id": str(proposal.public_id),
        "schema_version": proposal.schema_version,
        "proposal_group_id": str(proposal.proposal_group_id),
        "revision": proposal.revision,
        "parent_proposal_id": (
            str(proposal.parent_proposal.public_id)
            if proposal.parent_proposal is not None
            else None
        ),
        "proposal_hash": proposal.proposal_hash,
        "lifecycle": current_lifecycle(proposal).value,
        "organization_id": str(proposal.organization.public_id),
        "repository_id": str(repository.public_id),
        "snapshot_id": str(snapshot.public_id),
        "base_sha": snapshot.base_sha,
        "head_sha": snapshot.head_sha,
        "source_llm_evidence_id": str(source.public_id),
        "target_behavior": proposal.target_behavior,
        "rationale": proposal.rationale,
        "evidence_ids": proposal.evidence_ids,
        "file_path": proposal.file_path,
        "patch": proposal.patch,
        "commands": proposal.commands,
        "expected_result": proposal.expected_result,
        "risk": proposal.risk,
        "test_adapter": proposal.test_adapter,
        "test_adapter_version": proposal.test_adapter_version,
        "generation_metadata": proposal.generation_metadata,
        "validation_report": proposal.validation_report,
        "advisory_only": True,
        "accepted_for_export_is_execution_approval": False,
        "created_at": proposal.created_at.isoformat(),
    }
