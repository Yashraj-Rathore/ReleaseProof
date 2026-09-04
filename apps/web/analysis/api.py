"""Read-only tenant-scoped API for persisted agent investigations."""

from __future__ import annotations

import uuid

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.web.analysis.agent_investigation import (
    get_agent_investigation,
    serialize_agent_investigation,
)
from apps.web.organizations.views import active_organization


class AgentInvestigationDetailView(APIView):  # type: ignore[misc]
    def get(self, request: Request, public_id: uuid.UUID) -> Response:
        organization = active_organization(request._request)
        item = get_agent_investigation(organization=organization, public_id=public_id)
        return Response(serialize_agent_investigation(item))
