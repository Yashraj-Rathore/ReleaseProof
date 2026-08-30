"""Evidence-first HTML views for current model and persisted snapshot risk."""

from __future__ import annotations

import uuid

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.web.organizations.views import active_organization
from apps.web.risk.artifacts import safe_current_model_summary
from apps.web.risk.services import get_current_risk_score, serialize_risk_score


@login_required
@require_GET
def current_model_view(request: HttpRequest) -> HttpResponse:
    organization = active_organization(request)
    return render(
        request,
        "risk/current_model.html",
        {
            "organization": organization,
            "summary": safe_current_model_summary(),
        },
    )


@login_required
@require_GET
def snapshot_risk_view(request: HttpRequest, snapshot_public_id: uuid.UUID) -> HttpResponse:
    organization = active_organization(request)
    score = get_current_risk_score(
        organization=organization,
        snapshot_public_id=snapshot_public_id,
    )
    return render(
        request,
        "risk/snapshot_risk.html",
        {"organization": organization, "risk": serialize_risk_score(score)},
    )
