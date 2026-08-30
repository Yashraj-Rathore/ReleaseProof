"""Tenant-scoped read APIs for model selection and persisted risk evidence."""

from __future__ import annotations

import uuid

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.web.organizations.views import active_organization
from apps.web.risk.artifacts import safe_current_model_summary
from apps.web.risk.services import get_current_risk_score, serialize_risk_score


class CurrentModelView(APIView):  # type: ignore[misc]
    def get(self, request: Request) -> Response:
        active_organization(request._request)
        return Response(safe_current_model_summary())


class SnapshotRiskView(APIView):  # type: ignore[misc]
    def get(self, request: Request, snapshot_public_id: uuid.UUID) -> Response:
        organization = active_organization(request._request)
        score = get_current_risk_score(
            organization=organization,
            snapshot_public_id=snapshot_public_id,
        )
        return Response(serialize_risk_score(score))
