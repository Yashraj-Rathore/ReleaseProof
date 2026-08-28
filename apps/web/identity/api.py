"""Authenticated identity API."""

from __future__ import annotations

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.web.organizations.models import Membership


class MeView(APIView):  # type: ignore[misc]
    def get(self, request: Request) -> Response:
        memberships = (
            Membership.objects.active()
            .filter(user_id=request.user.pk)
            .select_related("organization")
            .order_by("organization__name")
        )
        return Response(
            {
                "user": {
                    "username": request.user.get_username(),
                },
                "organizations": [
                    {
                        "id": str(membership.organization.public_id),
                        "name": membership.organization.name,
                        "role": membership.role,
                    }
                    for membership in memberships
                ],
            }
        )
