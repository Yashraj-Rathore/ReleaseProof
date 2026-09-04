"""Human-visible safe agent trace without hidden chain-of-thought."""

from __future__ import annotations

import uuid

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.web.analysis.agent_investigation import (
    get_agent_investigation,
    serialize_agent_investigation,
)
from apps.web.organizations.views import active_organization


@login_required
@require_GET
def agent_investigation_detail_view(
    request: HttpRequest,
    public_id: uuid.UUID,
) -> HttpResponse:
    organization = active_organization(request)
    item = get_agent_investigation(organization=organization, public_id=public_id)
    return render(
        request,
        "analysis/agent_investigation_detail.html",
        {
            "organization": organization,
            "investigation": serialize_agent_investigation(item),
        },
    )
