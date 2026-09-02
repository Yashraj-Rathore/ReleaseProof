"""Server-rendered human review workflow for generated-test proposals."""

from __future__ import annotations

import uuid
from typing import cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AbstractBaseUser
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.web.organizations.models import MembershipRole, Organization
from apps.web.organizations.services import require_minimum_role
from apps.web.organizations.views import active_organization
from apps.web.verification.execution_services import (
    ExecutionWorkflowError,
    _load_plan,
    approve_execution_plan,
    serialize_execution_plan,
)
from apps.web.verification.models import ProposalLifecycle
from apps.web.verification.services import (
    ProposalWorkflowError,
    edit_test_proposal,
    export_test_proposal,
    get_test_proposal,
    serialize_test_proposal,
    transition_test_proposal,
)
from packages.ai_core import GeneratedTestProposalV1, ProposalRisk


def _reviewer(request: HttpRequest) -> tuple[Organization, AbstractBaseUser]:
    organization = active_organization(request)
    require_minimum_role(
        user=request.user,
        organization=organization,
        minimum_role=MembershipRole.REVIEWER,
    )
    return organization, cast(AbstractBaseUser, request.user)


@login_required
@require_GET
def test_proposal_detail_view(request: HttpRequest, public_id: uuid.UUID) -> HttpResponse:
    organization = active_organization(request)
    proposal = get_test_proposal(organization=organization, public_id=public_id)
    return render(
        request,
        "verification/test_proposal_detail.html",
        {
            "organization": organization,
            "proposal": serialize_test_proposal(proposal),
        },
    )


def _transition_response(
    request: HttpRequest,
    *,
    public_id: uuid.UUID,
    target: ProposalLifecycle,
) -> HttpResponse:
    organization, actor = _reviewer(request)
    try:
        result = transition_test_proposal(
            organization=organization,
            proposal_public_id=public_id,
            target=target,
            actor=actor,
        )
    except ProposalWorkflowError:
        return HttpResponseBadRequest("Proposal transition is not allowed.")
    return redirect("test-proposal-detail", public_id=result.proposal.public_id)


@login_required
@require_POST
def accept_test_proposal_view(request: HttpRequest, public_id: uuid.UUID) -> HttpResponse:
    return _transition_response(
        request,
        public_id=public_id,
        target=ProposalLifecycle.ACCEPTED_FOR_EXPORT,
    )


@login_required
@require_POST
def reject_test_proposal_view(request: HttpRequest, public_id: uuid.UUID) -> HttpResponse:
    return _transition_response(
        request,
        public_id=public_id,
        target=ProposalLifecycle.REJECTED,
    )


@login_required
@require_POST
def edit_test_proposal_view(request: HttpRequest, public_id: uuid.UUID) -> HttpResponse:
    organization, actor = _reviewer(request)
    proposal = get_test_proposal(
        organization=organization,
        public_id=public_id,
    )
    current = proposal.as_contract()
    try:
        replacement = GeneratedTestProposalV1(
            schema_version=current.schema_version,
            target_behavior=request.POST.get("target_behavior", ""),
            rationale=request.POST.get("rationale", ""),
            evidence_ids=current.evidence_ids,
            file_path=request.POST.get("file_path", ""),
            patch=request.POST.get("patch", ""),
            commands=tuple(
                line.strip()
                for line in request.POST.get("commands", "").splitlines()
                if line.strip()
            ),
            expected_result=request.POST.get("expected_result", ""),
            risk=ProposalRisk(request.POST.get("risk", "")),
            test_adapter=current.test_adapter,
            test_adapter_version=current.test_adapter_version,
            generation=current.generation,
        )
        result = edit_test_proposal(
            organization=organization,
            proposal_public_id=public_id,
            replacement=replacement,
            actor=actor,
        )
    except (ProposalWorkflowError, TypeError, ValueError):
        return HttpResponseBadRequest("Proposal edit is invalid.")
    return redirect("test-proposal-detail", public_id=result.proposal.public_id)


@login_required
@require_POST
def export_test_proposal_view(request: HttpRequest, public_id: uuid.UUID) -> HttpResponse:
    organization, actor = _reviewer(request)
    try:
        exported = export_test_proposal(
            organization=organization,
            proposal_public_id=public_id,
            actor=actor,
        )
    except ProposalWorkflowError:
        return HttpResponseBadRequest("Proposal is not eligible for export.")
    response = HttpResponse(exported.patch, content_type="text/x-diff; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{exported.filename}"'
    response["Cache-Control"] = "no-store"
    response["X-ReleaseProof-Proposal-SHA256"] = exported.proposal.proposal_hash
    response["X-ReleaseProof-Correlation-ID"] = str(exported.correlation_id)
    return response


@login_required
@require_GET
def execution_plan_detail_view(request: HttpRequest, public_id: uuid.UUID) -> HttpResponse:
    organization = active_organization(request)
    try:
        plan = _load_plan(organization=organization, public_id=public_id)
    except ExecutionWorkflowError:
        from django.http import Http404

        raise Http404 from None
    return render(
        request,
        "verification/execution_plan_detail.html",
        {"organization": organization, "execution_plan": serialize_execution_plan(plan)},
    )


@login_required
@require_POST
def approve_execution_plan_view(request: HttpRequest, public_id: uuid.UUID) -> HttpResponse:
    organization, actor = _reviewer(request)
    try:
        result = approve_execution_plan(
            organization=organization,
            plan_public_id=public_id,
            actor=actor,
        )
    except ExecutionWorkflowError:
        return HttpResponseBadRequest("Execution plan approval is not allowed.")
    return redirect("execution-plan-detail", public_id=result.approval.plan.public_id)
