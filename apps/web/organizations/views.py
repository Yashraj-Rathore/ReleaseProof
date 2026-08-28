"""Same-origin organization context mutations."""

from __future__ import annotations

import uuid

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from apps.web.organizations.models import Organization
from apps.web.organizations.services import require_organization

ACTIVE_ORGANIZATION_SESSION_KEY = "releaseproof.organization_public_id"


@login_required
@require_POST
def select_organization(request: HttpRequest, public_id: uuid.UUID) -> HttpResponse:
    organization = require_organization(request.user, public_id)
    request.session.cycle_key()
    request.session[ACTIVE_ORGANIZATION_SESSION_KEY] = str(organization.public_id)
    return redirect("api-me")


def active_organization(request: HttpRequest) -> Organization:
    public_id = request.session.get(ACTIVE_ORGANIZATION_SESSION_KEY)
    if not isinstance(public_id, str):
        raise Http404("active organization not selected")
    return require_organization(request.user, public_id)
