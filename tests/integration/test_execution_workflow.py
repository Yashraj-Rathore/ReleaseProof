from __future__ import annotations

import uuid

import pytest
from django.db import DatabaseError, connection, transaction

from apps.web.verification.execution_services import (
    approve_execution_plan,
    create_execution_plan,
    record_execution_result,
)
from apps.web.verification.models import (
    ExecutionApproval,
    ExecutionPlan,
    ExecutionRun,
    ProposalLifecycle,
)
from apps.web.verification.services import create_test_proposal, transition_test_proposal
from packages.execution_contracts import (
    ExecutionOutcome,
    ExecutionResultV1,
    SafeOutputV1,
    sign_payload,
)
from tests import factories
from tests.integration.test_generated_test_proposals import _proposal, _source

pytestmark = pytest.mark.django_db


def _approved_proposal(*, suffix: str, number: int) -> tuple[object, object, object]:
    organization, _repository, _feature_set, source = _source(suffix=suffix, number=number)
    reviewer = factories.user(username=f"{suffix}-runner-reviewer")
    proposal = create_test_proposal(
        organization=organization,  # type: ignore[arg-type]
        source_llm_evidence_public_id=source.public_id,
        proposal=_proposal(source),  # type: ignore[arg-type]
        actor=reviewer,
    ).proposal
    transition_test_proposal(
        organization=organization,  # type: ignore[arg-type]
        proposal_public_id=proposal.public_id,
        target=ProposalLifecycle.ACCEPTED_FOR_EXPORT,
        actor=reviewer,
    )
    return organization, reviewer, proposal


def test_plan_approval_and_result_are_separate_immutable_idempotent_events() -> None:
    organization, reviewer, proposal = _approved_proposal(suffix="m9-workflow", number=61)
    created = create_execution_plan(
        organization=organization,  # type: ignore[arg-type]
        proposal=proposal,  # type: ignore[arg-type]
        image_digest=f"sha256:{'d' * 64}",
        actor=reviewer,  # type: ignore[arg-type]
    )
    repeated = create_execution_plan(
        organization=organization,  # type: ignore[arg-type]
        proposal=proposal,  # type: ignore[arg-type]
        image_digest=f"sha256:{'d' * 64}",
        actor=reviewer,  # type: ignore[arg-type]
    )

    assert created.created is True
    assert repeated.created is False
    assert created.plan.pk == repeated.plan.pk
    assert not ExecutionApproval.objects.filter(plan=created.plan).exists()
    approval = approve_execution_plan(
        organization=organization,  # type: ignore[arg-type]
        plan_public_id=created.plan.public_id,
        actor=reviewer,  # type: ignore[arg-type]
    )
    duplicate_approval = approve_execution_plan(
        organization=organization,  # type: ignore[arg-type]
        plan_public_id=created.plan.public_id,
        actor=reviewer,  # type: ignore[arg-type]
    )
    assert approval.created is True
    assert duplicate_approval.created is False

    empty = SafeOutputV1.capture(b"", limit=65_536)
    result = ExecutionResultV1(
        plan_sha256=created.contract.plan_sha256,
        image=created.contract.image,
        attempt=1,
        outcome=ExecutionOutcome.PASSED,
        elapsed_milliseconds=20,
        exit_code=0,
        stdout=empty,
        stderr=empty,
        timed_out=False,
        killed=False,
        cleanup_succeeded=True,
        isolation_checks=(("fixture_boundary", True),),
    )
    key = b"m9-result-signing-key-is-at-least-32-bytes"
    result_signature = sign_payload(result.canonical_bytes(), key=key)
    idempotency_key = uuid.uuid4()
    recorded = record_execution_result(
        organization=organization,  # type: ignore[arg-type]
        plan_public_id=created.plan.public_id,
        result=result,
        result_signature=result_signature,
        signing_key=key,
        idempotency_key=idempotency_key,
    )
    duplicate = record_execution_result(
        organization=organization,  # type: ignore[arg-type]
        plan_public_id=created.plan.public_id,
        result=result,
        result_signature=result_signature,
        signing_key=key,
        idempotency_key=idempotency_key,
    )
    assert recorded.created is True
    assert duplicate.created is False
    assert recorded.run.pk == duplicate.run.pk
    assert recorded.run.payload["stdout"]["excerpt"] == ""

    table = connection.ops.quote_name(ExecutionRun._meta.db_table)
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f"UPDATE {table} SET attempt = %s WHERE id = %s", [2, recorded.run.id])  # noqa: S608


def test_execution_relationships_reject_cross_tenant_approval() -> None:
    organization, reviewer, proposal = _approved_proposal(suffix="m9-tenant-a", number=62)
    other, _other_reviewer, _other_proposal = _approved_proposal(suffix="m9-tenant-b", number=63)
    created = create_execution_plan(
        organization=organization,  # type: ignore[arg-type]
        proposal=proposal,  # type: ignore[arg-type]
        image_digest=f"sha256:{'e' * 64}",
        actor=reviewer,  # type: ignore[arg-type]
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        ExecutionApproval.objects.create(
            organization=other,
            plan=created.plan,
            snapshot_head_sha=created.plan.snapshot_head_sha,
            proposal_hash=created.plan.proposal_hash,
            plan_hash=created.plan.plan_hash,
            actor=reviewer,
            correlation_id=uuid.uuid4(),
        )

    assert ExecutionPlan.objects.filter(organization=other, id=created.plan.id).count() == 0
