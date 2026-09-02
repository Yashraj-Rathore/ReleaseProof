"""Authenticated tenant-scoped generated-test proposal API."""

from __future__ import annotations

import json
import uuid

from django.http import HttpResponse
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.web.organizations.models import MembershipRole
from apps.web.organizations.services import require_minimum_role
from apps.web.organizations.views import active_organization
from apps.web.verification.models import ProposalLifecycle
from apps.web.verification.services import (
    ProposalWorkflowError,
    edit_test_proposal,
    export_test_proposal,
    get_test_proposal,
    serialize_test_proposal,
    transition_test_proposal,
)
from packages.ai_core import ProposalSchemaError, parse_test_proposal_json


def _invalid(code: str, *, status: int = 400) -> Response:
    return Response(
        {
            "error": {
                "code": code,
                "message": "The generated-test proposal action is not allowed.",
                "correlation_id": str(uuid.uuid4()),
                "details": {},
            }
        },
        status=status,
    )


class TestProposalDetailView(APIView):  # type: ignore[misc]
    def get(self, request: Request, public_id: uuid.UUID) -> Response:
        organization = active_organization(request._request)
        proposal = get_test_proposal(organization=organization, public_id=public_id)
        return Response(serialize_test_proposal(proposal))


class TestProposalTransitionView(APIView):  # type: ignore[misc]
    target: ProposalLifecycle

    def post(self, request: Request, public_id: uuid.UUID) -> Response:
        organization = active_organization(request._request)
        require_minimum_role(
            user=request.user,
            organization=organization,
            minimum_role=MembershipRole.REVIEWER,
        )
        try:
            result = transition_test_proposal(
                organization=organization,
                proposal_public_id=public_id,
                target=self.target,
                actor=request.user,
            )
        except ProposalWorkflowError as error:
            return _invalid(error.code)
        payload = serialize_test_proposal(result.proposal)
        payload["transition_created"] = result.created
        payload["correlation_id"] = str(result.correlation_id)
        return Response(payload)


class AcceptTestProposalView(TestProposalTransitionView):
    target = ProposalLifecycle.ACCEPTED_FOR_EXPORT


class RejectTestProposalView(TestProposalTransitionView):
    target = ProposalLifecycle.REJECTED


class EditTestProposalView(APIView):  # type: ignore[misc]
    def post(self, request: Request, public_id: uuid.UUID) -> Response:
        organization = active_organization(request._request)
        require_minimum_role(
            user=request.user,
            organization=organization,
            minimum_role=MembershipRole.REVIEWER,
        )
        try:
            raw = json.dumps(
                request.data,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
            )
            replacement = parse_test_proposal_json(raw)
            result = edit_test_proposal(
                organization=organization,
                proposal_public_id=public_id,
                replacement=replacement,
                actor=request.user,
            )
        except (ProposalSchemaError, TypeError, ValueError) as error:
            code = (
                error.code
                if isinstance(error, ProposalWorkflowError)
                else "proposal_schema_invalid"
            )
            return _invalid(code)
        payload = serialize_test_proposal(result.proposal)
        payload["revision_created"] = result.created
        payload["correlation_id"] = str(result.correlation_id)
        return Response(payload, status=201 if result.created else 200)


class ExportTestProposalView(APIView):  # type: ignore[misc]
    def post(self, request: Request, public_id: uuid.UUID) -> HttpResponse | Response:
        organization = active_organization(request._request)
        require_minimum_role(
            user=request.user,
            organization=organization,
            minimum_role=MembershipRole.REVIEWER,
        )
        try:
            exported = export_test_proposal(
                organization=organization,
                proposal_public_id=public_id,
                actor=request.user,
            )
        except ProposalWorkflowError as error:
            return _invalid(error.code)
        response = HttpResponse(exported.patch, content_type="text/x-diff; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{exported.filename}"'
        response["Cache-Control"] = "no-store"
        response["X-ReleaseProof-Proposal-SHA256"] = exported.proposal.proposal_hash
        response["X-ReleaseProof-Correlation-ID"] = str(exported.correlation_id)
        return response
