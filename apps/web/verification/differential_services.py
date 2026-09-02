"""Tenant-scoped M10 differential evidence and recommendation persistence."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from apps.web.audit.services import record_audit
from apps.web.evidence.models import EvidenceItem, EvidenceKind
from apps.web.organizations.models import Organization
from apps.web.risk.models import RiskScore
from apps.web.verification.execution_services import execution_plan_is_active
from apps.web.verification.models import (
    DifferentialPlan,
    DifferentialRun,
    ExecutionApproval,
    ExecutionPlan,
    ExecutionRun,
    ProposalLifecycle,
    RecommendationDecision,
)
from apps.web.verification.services import current_lifecycle
from packages.execution_contracts import (
    BASE_FIXTURE_SHA,
    DifferentialOutcome,
    DifferentialPlanV1,
    DifferentialResultV1,
    ExecutionOutcome,
    FixtureExecutionInputV1,
    parse_differential_plan_json,
    parse_execution_plan_json,
    verify_payload_signature,
)
from packages.ml_core import RiskBand
from packages.recommendation_core import (
    ComponentStatus,
    RecommendationInputsV1,
    fuse_recommendation,
)


class DifferentialWorkflowError(ValueError):
    """A safe, stable rejection at an M10 application boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class DifferentialPlanCreation:
    plan: DifferentialPlan
    contract: DifferentialPlanV1
    execution_input: FixtureExecutionInputV1
    created: bool
    correlation_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class DifferentialRunRecording:
    run: DifferentialRun
    created: bool
    correlation_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class RecommendationRecording:
    decision: RecommendationDecision
    created: bool
    correlation_id: uuid.UUID


def _load_plan(
    *, organization: Organization, public_id: uuid.UUID | str, lock: bool = False
) -> DifferentialPlan:
    query = DifferentialPlan.objects.for_organization(organization).select_related(
        "source_approval",
        "source_execution_plan__proposal__source_llm_evidence__snapshot__repository",
        "source_execution_plan__snapshot",
    )
    if lock:
        query = query.select_for_update()
    try:
        normalized = uuid.UUID(str(public_id))
    except ValueError as error:
        raise DifferentialWorkflowError("differential_plan_invalid") from error
    plan = query.filter(public_id=normalized).first()
    if plan is None:
        raise DifferentialWorkflowError("differential_plan_unavailable")
    return plan


@transaction.atomic
def create_differential_plan(
    *,
    organization: Organization,
    execution_plan: ExecutionPlan,
    candidate_variant: str,
    actor: AbstractBaseUser,
) -> DifferentialPlanCreation:
    """Create a parity plan chained to the still-current separately approved M9 plan."""

    source = (
        ExecutionPlan.objects.select_for_update()
        .select_related("proposal__source_llm_evidence__snapshot__repository", "snapshot")
        .filter(organization=organization, pk=execution_plan.pk)
        .first()
    )
    if source is None:
        raise DifferentialWorkflowError("execution_plan_unavailable")
    approval = ExecutionApproval.objects.filter(organization=organization, plan=source).first()
    if approval is None:
        raise DifferentialWorkflowError("execution_not_approved")
    if not execution_plan_is_active(source):
        raise DifferentialWorkflowError("execution_plan_stale")
    snapshot = source.snapshot
    if snapshot.base_sha != BASE_FIXTURE_SHA:
        raise DifferentialWorkflowError("differential_base_not_controlled")
    proposal = source.proposal
    execution_input = FixtureExecutionInputV1(
        proposal_hash=proposal.proposal_hash,
        file_path=proposal.file_path,
        patch=proposal.patch,
    )
    source_contract = parse_execution_plan_json(json.dumps(source.payload, sort_keys=True))
    try:
        contract = DifferentialPlanV1(
            organization_id=str(organization.public_id),
            repository_id=str(snapshot.repository.public_id),
            snapshot_id=str(snapshot.public_id),
            execution_plan_id=str(source.public_id),
            execution_approval_id=str(approval.public_id),
            execution_plan_sha256=source.plan_hash,
            proposal_hash=source.proposal_hash,
            proposal_input_sha256=execution_input.input_sha256,
            base_sha=snapshot.base_sha,
            candidate_sha=snapshot.head_sha,
            candidate_variant=candidate_variant,
            image=source.image,
            resources=source_contract.resources,
            host_profile=source_contract.host_profile,
        )
    except ValueError as error:
        raise DifferentialWorkflowError("differential_plan_contract_invalid") from error
    existing = DifferentialPlan.objects.filter(
        organization=organization, plan_hash=contract.plan_sha256
    ).first()
    correlation_id = uuid.uuid4()
    if existing is not None:
        return DifferentialPlanCreation(existing, contract, execution_input, False, correlation_id)
    plan = DifferentialPlan(
        organization=organization,
        source_execution_plan=source,
        source_approval=approval,
        schema_version=contract.schema_version,
        plan_hash=contract.plan_sha256,
        base_sha=contract.base_sha,
        candidate_sha=contract.candidate_sha,
        image=contract.image,
        payload=contract.as_dict(),
        created_by_id=actor.pk,
    )
    plan.full_clean()
    plan.save()
    record_audit(
        organization=organization,
        action="differential_plan.created",
        resource_type="differential_plan",
        resource_public_id=plan.public_id,
        correlation_id=correlation_id,
        actor=actor,
        metadata={
            "base_sha": plan.base_sha,
            "candidate_sha": plan.candidate_sha,
            "plan_hash": plan.plan_hash,
        },
    )
    return DifferentialPlanCreation(plan, contract, execution_input, True, correlation_id)


@transaction.atomic
def record_differential_result(
    *,
    organization: Organization,
    plan_public_id: uuid.UUID | str,
    result: DifferentialResultV1,
    result_signature: str,
    signing_key: bytes,
    idempotency_key: uuid.UUID,
) -> DifferentialRunRecording:
    plan = _load_plan(organization=organization, public_id=plan_public_id, lock=True)
    if not verify_payload_signature(
        result.canonical_bytes(), signature=result_signature, key=signing_key
    ):
        raise DifferentialWorkflowError("differential_result_signature_invalid")
    if result.plan_sha256 != plan.plan_hash or result.image != plan.image:
        raise DifferentialWorkflowError("differential_result_binding_invalid")
    plan_contract = parse_differential_plan_json(json.dumps(plan.payload, sort_keys=True))
    if tuple(item.mutation_id for item in result.mutations) != plan_contract.mutation_ids:
        raise DifferentialWorkflowError("differential_result_mutation_binding_invalid")
    existing = DifferentialRun.objects.filter(
        organization=organization, idempotency_key=idempotency_key
    ).first()
    if existing is None:
        existing = DifferentialRun.objects.filter(plan=plan, attempt=result.attempt).first()
    correlation_id = uuid.uuid4()
    if existing is not None:
        if existing.result_hash != result.result_sha256:
            raise DifferentialWorkflowError("differential_result_idempotency_conflict")
        return DifferentialRunRecording(existing, False, correlation_id)
    run = DifferentialRun(
        organization=organization,
        plan=plan,
        schema_version=result.schema_version,
        result_hash=result.result_sha256,
        attempt=result.attempt,
        outcome=result.outcome.value,
        mutation_killed=result.mutation_killed,
        mutation_total=result.mutation_total,
        idempotency_key=idempotency_key,
        stale_at_recording=not execution_plan_is_active(plan.source_execution_plan),
        payload=result.as_dict(),
    )
    run.full_clean()
    run.save()
    record_audit(
        organization=organization,
        action="differential_result.recorded",
        resource_type="differential_run",
        resource_public_id=run.public_id,
        correlation_id=correlation_id,
        metadata={
            "mutation_killed": run.mutation_killed,
            "mutation_total": run.mutation_total,
            "outcome": run.outcome,
            "plan_hash": plan.plan_hash,
            "stale": run.stale_at_recording,
        },
    )
    return DifferentialRunRecording(run, True, correlation_id)


def _single_uuid(evidence_ids: tuple[str, ...], prefix: str) -> uuid.UUID:
    if len(evidence_ids) != 1 or not evidence_ids[0].startswith(prefix):
        raise DifferentialWorkflowError("recommendation_evidence_binding_invalid")
    try:
        return uuid.UUID(evidence_ids[0].removeprefix(prefix))
    except ValueError as error:
        raise DifferentialWorkflowError("recommendation_evidence_binding_invalid") from error


def _validate_available_lineage(
    *, organization: Organization, run: DifferentialRun, inputs: RecommendationInputsV1
) -> None:
    snapshot = run.plan.source_execution_plan.snapshot
    proposal = run.plan.source_execution_plan.proposal
    if inputs.model_risk.status is ComponentStatus.AVAILABLE:
        risk_id = _single_uuid(inputs.model_risk.evidence_ids, "risk_score:")
        risk = (
            RiskScore.objects.for_organization(organization)
            .filter(public_id=risk_id, snapshot=snapshot)
            .first()
        )
        if (
            risk is None
            or risk.band == RiskBand.UNKNOWN
            or inputs.model_risk.deterministic_hold != (risk.band == RiskBand.HIGH)
        ):
            raise DifferentialWorkflowError("recommendation_risk_binding_invalid")
    if inputs.retrieval.status is ComponentStatus.AVAILABLE:
        evidence_id = _single_uuid(inputs.retrieval.evidence_ids, "evidence:")
        if (
            not EvidenceItem.objects.for_organization(organization)
            .filter(
                public_id=evidence_id,
                snapshot=snapshot,
                kind=EvidenceKind.RETRIEVAL,
                missing=False,
            )
            .exists()
        ):
            raise DifferentialWorkflowError("recommendation_retrieval_binding_invalid")
    if inputs.generated_tests.status is ComponentStatus.AVAILABLE:
        proposal_id = _single_uuid(inputs.generated_tests.evidence_ids, "generated_test_proposal:")
        if (
            proposal.public_id != proposal_id
            or current_lifecycle(proposal) is not ProposalLifecycle.ACCEPTED_FOR_EXPORT
        ):
            raise DifferentialWorkflowError("recommendation_test_binding_invalid")
    if inputs.execution.status is ComponentStatus.AVAILABLE:
        execution_id = _single_uuid(inputs.execution.evidence_ids, "execution_run:")
        execution = ExecutionRun.objects.filter(
            organization=organization,
            public_id=execution_id,
            plan=run.plan.source_execution_plan,
        ).first()
        if execution is None:
            raise DifferentialWorkflowError("recommendation_execution_binding_invalid")
        if execution.stale_at_recording or execution.outcome not in {
            ExecutionOutcome.PASSED,
            ExecutionOutcome.FAILED,
        }:
            raise DifferentialWorkflowError("recommendation_execution_binding_invalid")
        should_hold = execution.outcome == ExecutionOutcome.FAILED
        if inputs.execution.deterministic_hold != should_hold:
            raise DifferentialWorkflowError("recommendation_execution_binding_invalid")
    for component in (inputs.differential, inputs.mutation):
        if component.status is ComponentStatus.AVAILABLE:
            differential_id = _single_uuid(component.evidence_ids, "differential_run:")
            if differential_id != run.public_id:
                raise DifferentialWorkflowError("recommendation_differential_binding_invalid")
    if inputs.differential.status is ComponentStatus.AVAILABLE:
        if run.stale_at_recording or run.outcome not in {
            DifferentialOutcome.NO_DIFFERENCE,
            DifferentialOutcome.DIFFERENCE,
        }:
            raise DifferentialWorkflowError("recommendation_differential_binding_invalid")
        should_hold = run.outcome == DifferentialOutcome.DIFFERENCE
        if inputs.differential.deterministic_hold != should_hold:
            raise DifferentialWorkflowError("recommendation_differential_binding_invalid")
    if inputs.mutation.status is ComponentStatus.AVAILABLE:
        plan_contract = parse_differential_plan_json(json.dumps(run.plan.payload, sort_keys=True))
        if run.stale_at_recording or run.mutation_total != len(plan_contract.mutation_ids):
            raise DifferentialWorkflowError("recommendation_mutation_binding_invalid")
        expected_score = run.mutation_killed * 100 // run.mutation_total
        if inputs.mutation_score_percent != expected_score:
            raise DifferentialWorkflowError("recommendation_mutation_binding_invalid")


@transaction.atomic
def record_recommendation_decision(
    *,
    organization: Organization,
    differential_run: DifferentialRun,
    inputs: RecommendationInputsV1,
    actor: AbstractBaseUser,
) -> RecommendationRecording:
    run = (
        DifferentialRun.objects.select_for_update()
        .select_related(
            "plan__source_execution_plan__proposal",
            "plan__source_execution_plan__snapshot",
        )
        .filter(organization=organization, pk=differential_run.pk)
        .first()
    )
    if run is None:
        raise DifferentialWorkflowError("differential_run_unavailable")
    _validate_available_lineage(organization=organization, run=run, inputs=inputs)
    fused = fuse_recommendation(inputs)
    existing = RecommendationDecision.objects.filter(
        organization=organization,
        differential_run=run,
        policy_version=fused.policy_version,
    ).first()
    correlation_id = uuid.uuid4()
    if existing is not None:
        if existing.decision_hash != fused.decision_sha256:
            raise DifferentialWorkflowError("recommendation_policy_idempotency_conflict")
        return RecommendationRecording(existing, False, correlation_id)
    snapshot = run.plan.source_execution_plan.snapshot
    decision = RecommendationDecision(
        organization=organization,
        snapshot=snapshot,
        differential_run=run,
        policy_version=fused.policy_version,
        recommendation=fused.recommendation.value,
        inputs_hash=fused.inputs_sha256,
        decision_hash=fused.decision_sha256,
        payload={"decision": fused.as_dict(), "inputs": inputs.as_dict()},
        created_by_id=actor.pk,
    )
    decision.full_clean()
    decision.save()
    record_audit(
        organization=organization,
        action="recommendation.recorded",
        resource_type="recommendation_decision",
        resource_public_id=decision.public_id,
        correlation_id=correlation_id,
        actor=actor,
        metadata={
            "decision_hash": decision.decision_hash,
            "policy_version": decision.policy_version,
            "recommendation": decision.recommendation,
        },
    )
    return RecommendationRecording(decision, True, correlation_id)
