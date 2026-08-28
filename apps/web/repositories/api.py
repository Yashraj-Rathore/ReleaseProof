"""Tenant-scoped repository API."""

from __future__ import annotations

import uuid

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.web.audit.services import record_audit
from apps.web.organizations.models import MembershipRole
from apps.web.organizations.services import require_minimum_role
from apps.web.organizations.views import active_organization
from apps.web.repositories.models import RepositoryLifecycle
from apps.web.repositories.services import get_repository, get_repository_binding


class RepositoryDetailView(APIView):  # type: ignore[misc]
    def get(self, request: Request, public_id: uuid.UUID) -> Response:
        organization = active_organization(request._request)
        repository = get_repository(organization=organization, public_id=public_id)
        return Response(
            {
                "id": str(repository.public_id),
                "github_repository_id": repository.github_repository_id,
                "full_name": repository.full_name,
                "default_branch": repository.default_branch,
                "lifecycle": repository.lifecycle,
                "analysis_enabled": repository.analysis_enabled,
            }
        )


class RepositoryLifecycleView(APIView):  # type: ignore[misc]
    def post(self, request: Request, public_id: uuid.UUID) -> Response:
        organization = active_organization(request._request)
        require_minimum_role(
            user=request.user,
            organization=organization,
            minimum_role=MembershipRole.ADMIN,
        )
        repository = get_repository_binding(organization=organization, public_id=public_id)
        action = request.data.get("action") if hasattr(request.data, "get") else None
        if action not in {"enable", "disable"}:
            return Response(
                {
                    "error": {
                        "code": "invalid_lifecycle_action",
                        "message": "action must be enable or disable",
                        "correlation_id": str(uuid.uuid4()),
                        "details": {},
                    }
                },
                status=400,
            )
        repository.lifecycle = (
            RepositoryLifecycle.ACTIVE if action == "enable" else RepositoryLifecycle.DISABLED
        )
        repository.save(update_fields=("lifecycle", "updated_at"))
        correlation_id = uuid.uuid4()
        record_audit(
            organization=organization,
            actor=request.user,
            action=f"repository.{action}",
            resource_type="repository",
            resource_public_id=repository.public_id,
            correlation_id=correlation_id,
        )
        return Response(
            {
                "id": str(repository.public_id),
                "lifecycle": repository.lifecycle,
                "correlation_id": str(correlation_id),
            }
        )
