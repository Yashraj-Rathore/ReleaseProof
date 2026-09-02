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
from apps.web.verification.api import (
    AcceptTestProposalView,
    ApproveExecutionPlanView,
    EditTestProposalView,
    ExecutionPlanDetailView,
    ExportTestProposalView,
    RejectTestProposalView,
    TestProposalDetailView,
)
from apps.web.verification.views import (
    accept_test_proposal_view,
    approve_execution_plan_view,
    edit_test_proposal_view,
    execution_plan_detail_view,
    export_test_proposal_view,
    reject_test_proposal_view,
    test_proposal_detail_view,
)

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
        "api/v1/test-proposals/<uuid:public_id>",
        TestProposalDetailView.as_view(),
        name="api-test-proposal-detail",
    ),
    path(
        "api/v1/test-proposals/<uuid:public_id>/accept",
        AcceptTestProposalView.as_view(),
        name="api-accept-test-proposal",
    ),
    path(
        "api/v1/test-proposals/<uuid:public_id>/reject",
        RejectTestProposalView.as_view(),
        name="api-reject-test-proposal",
    ),
    path(
        "api/v1/test-proposals/<uuid:public_id>/edit",
        EditTestProposalView.as_view(),
        name="api-edit-test-proposal",
    ),
    path(
        "api/v1/test-proposals/<uuid:public_id>/export",
        ExportTestProposalView.as_view(),
        name="api-export-test-proposal",
    ),
    path(
        "app/test-proposals/<uuid:public_id>/",
        test_proposal_detail_view,
        name="test-proposal-detail",
    ),
    path(
        "app/test-proposals/<uuid:public_id>/accept/",
        accept_test_proposal_view,
        name="accept-test-proposal",
    ),
    path(
        "app/test-proposals/<uuid:public_id>/reject/",
        reject_test_proposal_view,
        name="reject-test-proposal",
    ),
    path(
        "app/test-proposals/<uuid:public_id>/edit/",
        edit_test_proposal_view,
        name="edit-test-proposal",
    ),
    path(
        "app/test-proposals/<uuid:public_id>/export/",
        export_test_proposal_view,
        name="export-test-proposal",
    ),
    path(
        "api/v1/execution-plans/<uuid:public_id>",
        ExecutionPlanDetailView.as_view(),
        name="api-execution-plan-detail",
    ),
    path(
        "api/v1/execution-plans/<uuid:public_id>/approve",
        ApproveExecutionPlanView.as_view(),
        name="api-approve-execution-plan",
    ),
    path(
        "app/execution-plans/<uuid:public_id>/",
        execution_plan_detail_view,
        name="execution-plan-detail",
    ),
    path(
        "app/execution-plans/<uuid:public_id>/approve/",
        approve_execution_plan_view,
        name="approve-execution-plan",
    ),
    path(
        "app/risk/snapshots/<uuid:snapshot_public_id>/",
        snapshot_risk_view,
        name="snapshot-risk",
    ),
    path("health/live", health.live, name="health-live"),
    path("health/ready", health.ready, name="health-ready"),
    path("webhooks/github", github_webhook, name="github-webhook"),
]
