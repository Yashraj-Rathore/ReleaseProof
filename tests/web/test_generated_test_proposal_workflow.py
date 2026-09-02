from __future__ import annotations

import json
from dataclasses import replace

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from adapters.test_generation.python_fixture import build_new_test_patch
from apps.web.analysis.models import AnalysisJob, OutboxEvent
from apps.web.organizations.models import MembershipRole
from apps.web.organizations.views import ACTIVE_ORGANIZATION_SESSION_KEY
from apps.web.verification.execution_services import create_execution_plan
from apps.web.verification.models import ProposalLifecycle
from apps.web.verification.services import (
    create_test_proposal,
    current_lifecycle,
    get_test_proposal,
)
from tests import factories
from tests.integration.test_generated_test_proposals import _proposal, _source
from tests.proposal_fixtures import VALID_TEST_PATH

pytestmark = pytest.mark.django_db


def _activate(client: Client, organization: object) -> None:
    session = client.session
    session[ACTIVE_ORGANIZATION_SESSION_KEY] = str(organization.public_id)  # type: ignore[attr-defined]
    session.save()


def _persisted_proposal(*, suffix: str, number: int, role: MembershipRole) -> tuple[object, ...]:
    organization, _repository, _feature_set, source = _source(suffix=suffix, number=number)
    account = factories.user(username=f"{suffix}-account")
    member = factories.membership(
        organization=organization,  # type: ignore[arg-type]
        user=account,
        role=role,
    )
    proposal = create_test_proposal(
        organization=organization,  # type: ignore[arg-type]
        source_llm_evidence_public_id=source.public_id,
        proposal=_proposal(source),  # type: ignore[arg-type]
        actor=account,
    ).proposal
    return organization, account, member, proposal


def test_detail_is_tenant_scoped_and_member_cannot_mutate() -> None:
    organization, account, member, proposal = _persisted_proposal(
        suffix="web-scope",
        number=51,
        role=MembershipRole.MEMBER,
    )
    other_organization, _repository, _feature_set, other_source = _source(
        suffix="web-other",
        number=52,
    )
    factories.membership(
        organization=other_organization,  # type: ignore[arg-type]
        user=account,
        role=MembershipRole.REVIEWER,
    )
    other_proposal = create_test_proposal(
        organization=other_organization,  # type: ignore[arg-type]
        source_llm_evidence_public_id=other_source.public_id,
        proposal=_proposal(other_source),  # type: ignore[arg-type]
        actor=account,
    ).proposal
    client = Client()
    client.force_login(account)
    _activate(client, organization)

    api = client.get(reverse("api-test-proposal-detail", args=[proposal.public_id]))
    page = client.get(reverse("test-proposal-detail", args=[proposal.public_id]))
    assert api.status_code == 200
    assert api.json()["accepted_for_export_is_execution_approval"] is False
    assert page.status_code == 200
    assert b"permits export only" in page.content
    assert (
        client.get(reverse("api-test-proposal-detail", args=[other_proposal.public_id])).status_code
        == 404
    )
    assert (
        client.get(reverse("test-proposal-detail", args=[other_proposal.public_id])).status_code
        == 404
    )
    assert (
        client.post(reverse("api-accept-test-proposal", args=[proposal.public_id])).status_code
        == 404
    )

    member.role = MembershipRole.REVIEWER  # type: ignore[attr-defined]
    member.save(update_fields=("role", "updated_at"))  # type: ignore[attr-defined]
    allowed = client.post(reverse("api-accept-test-proposal", args=[proposal.public_id]))
    assert allowed.status_code == 200
    assert allowed.json()["lifecycle"] == ProposalLifecycle.ACCEPTED_FOR_EXPORT


def test_browser_and_session_api_mutations_require_csrf_and_never_enqueue_execution() -> None:
    organization, account, _member, proposal = _persisted_proposal(
        suffix="web-csrf",
        number=53,
        role=MembershipRole.REVIEWER,
    )
    client = Client(enforce_csrf_checks=True)
    client.force_login(account)
    _activate(client, organization)
    assert client.get(reverse("test-proposal-detail", args=[proposal.public_id])).status_code == 200
    csrf_token = client.cookies[settings.CSRF_COOKIE_NAME].value
    job_count = AnalysisJob.objects.count()
    outbox_count = OutboxEvent.objects.count()

    endpoint = reverse("api-accept-test-proposal", args=[proposal.public_id])
    assert client.post(endpoint).status_code == 403
    accepted = client.post(endpoint, HTTP_X_CSRFTOKEN=csrf_token)
    assert accepted.status_code == 200
    assert accepted.json()["accepted_for_export_is_execution_approval"] is False
    assert accepted.json()["advisory_only"] is True

    export_endpoint = reverse("api-export-test-proposal", args=[proposal.public_id])
    assert client.post(export_endpoint).status_code == 403
    exported = client.post(export_endpoint, HTTP_X_CSRFTOKEN=csrf_token)
    assert exported.status_code == 200
    assert exported.content.decode() == proposal.patch
    assert exported["Cache-Control"] == "no-store"
    assert exported["X-ReleaseProof-Proposal-SHA256"] == proposal.proposal_hash
    assert AnalysisJob.objects.count() == job_count
    assert OutboxEvent.objects.count() == outbox_count


def test_reviewer_api_edit_creates_new_revision_then_can_reject_it() -> None:
    organization, account, _member, proposal = _persisted_proposal(
        suffix="web-edit",
        number=54,
        role=MembershipRole.REVIEWER,
    )
    client = Client()
    client.force_login(account)
    _activate(client, organization)
    content = (
        "from fixture_app.pricing import calculate_total\n\n\n"
        "def test_pricing_rounds_at_boundary() -> None:\n"
        "    assert calculate_total(200, 5) == 210\n"
    )
    replacement = replace(
        proposal.as_contract(),
        target_behavior="Pricing remains stable at the documented boundary.",
        patch=build_new_test_patch(file_path=VALID_TEST_PATH, content=content),
    )

    edited = client.post(
        reverse("api-edit-test-proposal", args=[proposal.public_id]),
        data=json.dumps(replacement.as_dict()),
        content_type="application/json",
    )
    assert edited.status_code == 201
    payload = edited.json()
    assert payload["revision"] == 2
    assert payload["parent_proposal_id"] == str(proposal.public_id)
    assert current_lifecycle(proposal) is ProposalLifecycle.SUPERSEDED
    revised = get_test_proposal(
        organization=organization,  # type: ignore[arg-type]
        public_id=payload["id"],
    )
    rejected = client.post(reverse("api-reject-test-proposal", args=[revised.public_id]))
    assert rejected.status_code == 200
    assert rejected.json()["lifecycle"] == ProposalLifecycle.REJECTED


def test_execution_approval_is_a_separate_reviewer_csrf_gated_exact_plan_action() -> None:
    organization, account, _member, proposal = _persisted_proposal(
        suffix="web-execution",
        number=55,
        role=MembershipRole.REVIEWER,
    )
    client = Client(enforce_csrf_checks=True)
    client.force_login(account)
    _activate(client, organization)
    assert client.get(reverse("test-proposal-detail", args=[proposal.public_id])).status_code == 200
    csrf_token = client.cookies[settings.CSRF_COOKIE_NAME].value
    accepted = client.post(
        reverse("api-accept-test-proposal", args=[proposal.public_id]),
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    assert accepted.status_code == 200
    created = create_execution_plan(
        organization=organization,  # type: ignore[arg-type]
        proposal=proposal,  # type: ignore[arg-type]
        image_digest=f"sha256:{'f' * 64}",
        actor=account,
    )
    endpoint = reverse("api-approve-execution-plan", args=[created.plan.public_id])

    assert (
        client.get(reverse("api-execution-plan-detail", args=[created.plan.public_id])).status_code
        == 200
    )
    assert client.post(endpoint).status_code == 403
    approved = client.post(endpoint, HTTP_X_CSRFTOKEN=csrf_token)
    assert approved.status_code == 200
    assert approved.json()["execution_approved"] is True
    assert approved.json()["currently_executable"] is True
    assert approved.json()["plan_hash"] == created.contract.plan_sha256
