"""Root URL configuration."""

from __future__ import annotations

from django.contrib import admin
from django.urls import path

from apps.web.changes.views import github_webhook
from apps.web.identity.api import MeView
from apps.web.identity.views import login_view, logout_view
from apps.web.organizations.views import select_organization
from apps.web.releaseproof import health
from apps.web.repositories.api import RepositoryDetailView, RepositoryLifecycleView
from apps.web.risk.api import CurrentModelView, SnapshotRiskView
from apps.web.risk.views import current_model_view, snapshot_risk_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", login_view, name="login"),
    path("accounts/logout/", logout_view, name="logout"),
    path("api/v1/me", MeView.as_view(), name="api-me"),
    path("api/v1/models/current", CurrentModelView.as_view(), name="api-current-model"),
    path(
        "api/v1/risk/snapshots/<uuid:snapshot_public_id>",
        SnapshotRiskView.as_view(),
        name="api-snapshot-risk",
    ),
    path(
        "api/v1/repositories/<uuid:public_id>",
        RepositoryDetailView.as_view(),
        name="api-repository-detail",
    ),
    path(
        "api/v1/repositories/<uuid:public_id>/lifecycle",
        RepositoryLifecycleView.as_view(),
        name="api-repository-lifecycle",
    ),
    path(
        "app/organizations/<uuid:public_id>/select/",
        select_organization,
        name="select-organization",
    ),
    path("app/models/current/", current_model_view, name="current-model"),
    path(
        "app/risk/snapshots/<uuid:snapshot_public_id>/",
        snapshot_risk_view,
        name="snapshot-risk",
    ),
    path("health/live", health.live, name="health-live"),
    path("health/ready", health.ready, name="health-ready"),
    path("webhooks/github", github_webhook, name="github-webhook"),
]
