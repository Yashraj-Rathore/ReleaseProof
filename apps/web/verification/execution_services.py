"""Tenant-scoped M9 plan, approval, and safe runner-result persistence."""

from __future__ import annotations

import shlex
import uuid
from dataclasses import dataclass

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from apps.web.audit.services import record_audit
from apps.web.changes.models import PullRequestSnapshot
from apps.web.organizations.models import Organization
from apps.web.verification.models import (
    ExecutionApproval,
    ExecutionPlan,
    ExecutionRun,
    GeneratedTestProposal,
    ProposalLifecycle,
)
from apps.web.verification.services import current_lifecycle
from packages.execution_contracts import (
    CONTROLLED_FIXTURE_TREE_SHA256,
    ExecutionPlanV1,
    ExecutionResultV1,
    FixtureExecutionInputV1,
    HostProfile,
    ResourceLimitsV1,
    verify_payload_signature,
)


class ExecutionWorkflowError(ValueError):
    """A safe, stable execution-workflow rejection."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class PlanCreationResult:
    plan: ExecutionPlan
    contract: ExecutionPlanV1
    execution_input: FixtureExecutionInputV1
    created: bool
    correlation_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    approval: ExecutionApproval
    created: bool
    correlation_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class RunRecordingResult:
    run: ExecutionRun
    created: bool
    correlation_id: uuid.UUID


def _latest_snapshot(snapshot: PullRequestSnapshot) -> PullRequestSnapshot | None:
    return (
        PullRequestSnapshot.objects.filter(
            organization=snapshot.organization,
            repository=snapshot.repository,
            pull_request_number=snapshot.pull_request_number,
        )
        .order_by("-created_at", "-id")
        .first()
    )


def _active(plan: ExecutionPlan) -> bool:
    latest = _latest_snapshot(plan.snapshot)
    return (
        latest is not None
        and latest.pk == plan.snapshot_id
        and latest.head_sha == plan.snapshot_head_sha
        and current_lifecycle(plan.proposal) is ProposalLifecycle.ACCEPTED_FOR_EXPORT
        and plan.proposal.proposal_hash == plan.proposal_hash
    )


def execution_plan_is_active(plan: ExecutionPlan) -> bool:
    """Expose the M9 freshness predicate to later evidence stages without weakening it."""

    return _active(plan)


def _load_plan(
    *, organization: Organization, public_id: uuid.UUID | str, lock: bool = False
) -> ExecutionPlan:
    query = ExecutionPlan.objects.for_organization(organization).select_related(
        "proposal__source_llm_evidence__snapshot__repository", "snapshot"
    )
    if lock:
        query = query.select_for_update()
    try:
        normalized = uuid.UUID(str(public_id))
    except ValueError as error:
        raise ExecutionWorkflowError("execution_plan_invalid") from error
    plan = query.filter(public_id=normalized).first()
    if plan is None:
        raise ExecutionWorkflowError("execution_plan_unavailable")
    return plan


@transaction.atomic
def create_execution_plan(
    *,
    organization: Organization,
    proposal: GeneratedTestProposal,
    image_digest: str,
    actor: AbstractBaseUser,
    host_profile: HostProfile = HostProfile.DEDICATED_ROOTLESS_FIXTURE,
    resources: ResourceLimitsV1 | None = None,
) -> PlanCreationResult:
    """Create an immutable plan; this deliberately does not approve or enqueue it."""

    locked = (
        GeneratedTestProposal.objects.select_for_update()
        .select_related("source_llm_evidence__snapshot__repository")
        .filter(pk=proposal.pk, organization=organization)
        .first()
    )
    if locked is None:
        raise ExecutionWorkflowError("proposal_unavailable")
    if current_lifecycle(locked) is not ProposalLifecycle.ACCEPTED_FOR_EXPORT:
        raise ExecutionWorkflowError("proposal_not_accepted_for_export")
    if not bool(locked.validation_report.get("valid", False)):
        raise ExecutionWorkflowError("proposal_static_validation_invalid")
    snapshot = locked.source_llm_evidence.snapshot
    if _latest_snapshot(snapshot).pk != snapshot.pk:  # type: ignore[union-attr]
        raise ExecutionWorkflowError("snapshot_stale")
    execution_input = FixtureExecutionInputV1(
        proposal_hash=locked.proposal_hash,
        file_path=locked.file_path,
        patch=locked.patch,
    )
    resolved_resources = resources or ResourceLimitsV1()
    try:
        commands = tuple(tuple(shlex.split(command, posix=True)) for command in locked.commands)
        contract = ExecutionPlanV1(
            organization_id=str(organization.public_id),
            repository_id=str(snapshot.repository.public_id),
            snapshot_id=str(snapshot.public_id),
            checkout_sha=snapshot.head_sha,
            proposal_id=str(locked.public_id),
            proposal_hash=locked.proposal_hash,
            proposal_input_sha256=execution_input.input_sha256,
            fixture_tree_sha256=CONTROLLED_FIXTURE_TREE_SHA256,
            image=f"releaseproof/fixture-runner@{image_digest}",
            commands=commands,
            resources=resolved_resources,
            host_profile=host_profile,
        )
    except ValueError as error:
        raise ExecutionWorkflowError("execution_plan_contract_invalid") from error
    existing = ExecutionPlan.objects.filter(
        organization=organization,
        plan_hash=contract.plan_sha256,
    ).first()
    correlation_id = uuid.uuid4()
    if existing is not None:
        return PlanCreationResult(existing, contract, execution_input, False, correlation_id)
    plan = ExecutionPlan(
        organization=organization,
        proposal=locked,
        snapshot=snapshot,
        schema_version=contract.schema_version,
        plan_hash=contract.plan_sha256,
        proposal_hash=locked.proposal_hash,
        snapshot_head_sha=snapshot.head_sha,
        image=contract.image,
        fixture_tree_sha256=contract.fixture_tree_sha256,
        payload=contract.as_dict(),
        created_by_id=actor.pk,
    )
    plan.full_clean()
    plan.save()
    record_audit(
        organization=organization,
        action="execution_plan.created",
        resource_type="execution_plan",
        resource_public_id=plan.public_id,
        correlation_id=correlation_id,
        actor=actor,
        metadata={"plan_hash": plan.plan_hash, "proposal_hash": plan.proposal_hash},
    )
    return PlanCreationResult(plan, contract, execution_input, True, correlation_id)


@transaction.atomic
def approve_execution_plan(
    *, organization: Organization, plan_public_id: uuid.UUID | str, actor: AbstractBaseUser
) -> ApprovalResult:
    """Append a distinct human approval for an exact still-current plan."""

    plan = _load_plan(organization=organization, public_id=plan_public_id, lock=True)
    if not _active(plan):
        raise ExecutionWorkflowError("execution_plan_stale")
    existing = ExecutionApproval.objects.filter(organization=organization, plan=plan).first()
    correlation_id = uuid.uuid4()
    if existing is not None:
        return ApprovalResult(existing, False, existing.correlation_id)
    approval = ExecutionApproval(
        organization=organization,
        plan=plan,
        snapshot_head_sha=plan.snapshot_head_sha,
        proposal_hash=plan.proposal_hash,
        plan_hash=plan.plan_hash,
        actor_id=actor.pk,
        correlation_id=correlation_id,
    )
    approval.full_clean()
    approval.save()
    record_audit(
        organization=organization,
        action="execution_plan.approved",
        resource_type="execution_plan",
        resource_public_id=plan.public_id,
        correlation_id=correlation_id,
        actor=actor,
        metadata={"plan_hash": plan.plan_hash, "proposal_hash": plan.proposal_hash},
    )
    return ApprovalResult(approval, True, correlation_id)


@transaction.atomic
def record_execution_result(
    *,
    organization: Organization,
    plan_public_id: uuid.UUID | str,
    result: ExecutionResultV1,
    result_signature: str,
    signing_key: bytes,
    idempotency_key: uuid.UUID,
) -> RunRecordingResult:
    """Authenticate and persist bounded result evidence; stale evidence remains explicit."""

    plan = _load_plan(organization=organization, public_id=plan_public_id, lock=True)
    if not verify_payload_signature(
        result.canonical_bytes(), signature=result_signature, key=signing_key
    ):
        raise ExecutionWorkflowError("execution_result_signature_invalid")
    if result.plan_sha256 != plan.plan_hash or result.image != plan.image:
        raise ExecutionWorkflowError("execution_result_binding_invalid")
    approval = ExecutionApproval.objects.filter(organization=organization, plan=plan).first()
    if approval is None:
        raise ExecutionWorkflowError("execution_not_approved")
    existing = ExecutionRun.objects.filter(
        organization=organization, idempotency_key=idempotency_key
    ).first()
    if existing is None:
        existing = ExecutionRun.objects.filter(plan=plan, attempt=result.attempt).first()
    correlation_id = uuid.uuid4()
    if existing is not None:
        if existing.result_hash != result.result_sha256:
            raise ExecutionWorkflowError("execution_result_idempotency_conflict")
        return RunRecordingResult(existing, False, correlation_id)
    run = ExecutionRun(
        organization=organization,
        plan=plan,
        approval=approval,
        schema_version=result.schema_version,
        result_hash=result.result_sha256,
        attempt=result.attempt,
        outcome=result.outcome.value,
        idempotency_key=idempotency_key,
        stale_at_recording=not _active(plan),
        payload=result.as_dict(),
    )
    run.full_clean()
    run.save()
    record_audit(
        organization=organization,
        action="execution_result.recorded",
        resource_type="execution_run",
        resource_public_id=run.public_id,
        correlation_id=correlation_id,
        metadata={
            "attempt": run.attempt,
            "outcome": run.outcome,
            "plan_hash": plan.plan_hash,
            "stale": run.stale_at_recording,
        },
    )
    return RunRecordingResult(run, True, correlation_id)


def serialize_execution_plan(plan: ExecutionPlan) -> dict[str, object]:
    approval = ExecutionApproval.objects.filter(plan=plan, organization=plan.organization).first()
    return {
        "id": str(plan.public_id),
        "schema_version": plan.schema_version,
        "plan_hash": plan.plan_hash,
        "proposal_id": str(plan.proposal.public_id),
        "proposal_hash": plan.proposal_hash,
        "snapshot_id": str(plan.snapshot.public_id),
        "snapshot_head_sha": plan.snapshot_head_sha,
        "image": plan.image,
        "fixture_tree_sha256": plan.fixture_tree_sha256,
        "payload": plan.payload,
        "execution_approved": approval is not None,
        "approval_id": str(approval.public_id) if approval is not None else None,
        "currently_executable": approval is not None and _active(plan),
        "created_at": plan.created_at.isoformat(),
    }
