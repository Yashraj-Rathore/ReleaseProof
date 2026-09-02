from __future__ import annotations

import uuid
from dataclasses import replace

import pytest
from django.db import DatabaseError, connection, transaction

from adapters.test_generation.python_fixture import build_new_test_patch
from apps.web.evidence.models import EvidenceItem, EvidenceKind
from apps.web.risk.models import RiskScore
from apps.web.verification.differential_services import (
    create_differential_plan,
    record_differential_result,
    record_recommendation_decision,
)
from apps.web.verification.execution_services import (
    approve_execution_plan,
    create_execution_plan,
    record_execution_result,
)
from apps.web.verification.models import (
    DifferentialRun,
    ProposalLifecycle,
    RecommendationDecision,
)
from apps.web.verification.services import create_test_proposal, transition_test_proposal
from packages.execution_contracts import (
    BASE_FIXTURE_SHA,
    DifferentialResultV1,
    ExecutionOutcome,
    ExecutionResultV1,
    MutationOutcome,
    MutationResultV1,
    SafeOutputV1,
    WorkloadObservationV1,
    WorkloadOutcome,
    compare_observations,
    sign_payload,
)
from packages.ml_core import RiskBand
from packages.recommendation_core import (
    ComponentEvidence,
    ComponentStatus,
    Recommendation,
    RecommendationInputsV1,
)
from tests import factories
from tests.integration.test_generated_test_proposals import _proposal, _source

pytestmark = pytest.mark.django_db

_CANDIDATE_SHA = "703143e8e75a685bd5385ec6f7e8016795451c8d"


def _observation(*, passed: bool, total: str) -> WorkloadObservationV1:
    empty = SafeOutputV1.capture(b"", limit=65_536)
    return WorkloadObservationV1(
        outcome=WorkloadOutcome.PASSED if passed else WorkloadOutcome.FAILED,
        test_exit_code=0 if passed else 1,
        test_elapsed_milliseconds=12,
        probe_exit_code=0,
        probe_elapsed_milliseconds=3,
        http={
            "body": {"currency": "CAD", "total": total},
            "headers": {"content-type": "application/json", "x-request-id": "masked"},
            "schema": {"currency": "string", "total": "string"},
            "status": 200,
        },
        state={"quote_count": 1, "updated_at": "masked"},
        events=({"name": "quote.calculated", "sequence": 1},),
        stdout=empty,
        stderr=empty,
    )


def _available(fact: str, evidence_id: str, *, hold: bool = False) -> ComponentEvidence:
    return ComponentEvidence(
        status=ComponentStatus.AVAILABLE,
        fact=fact,
        evidence_ids=(evidence_id,),
        deterministic_hold=hold,
    )


def test_approved_plan_to_differential_evidence_and_hold_recommendation_is_immutable() -> None:
    organization, _repository, feature_set, source = _source(
        suffix="m10-workflow",
        number=71,
        base_sha=BASE_FIXTURE_SHA,
        head_sha=_CANDIDATE_SHA,
    )
    reviewer = factories.user(username="m10-workflow-reviewer")
    file_path = "tests/generated/test_m10_quote.py"
    content = (
        "from fixture_app.pricing import Decimal, total_with_tax\n\n\n"
        "def test_quote_tax() -> None:\n"
        "    assert total_with_tax(Decimal('100'), Decimal('0.13')) == Decimal('113.00')\n"
    )
    proposal_contract = _proposal(
        source,
        file_path=file_path,
        patch=build_new_test_patch(file_path=file_path, content=content),
        commands=(f"python -m pytest -q {file_path}",),
    )
    proposal = create_test_proposal(
        organization=organization,  # type: ignore[arg-type]
        source_llm_evidence_public_id=source.public_id,
        proposal=proposal_contract,  # type: ignore[arg-type]
        actor=reviewer,
    ).proposal
    transition_test_proposal(
        organization=organization,  # type: ignore[arg-type]
        proposal_public_id=proposal.public_id,
        target=ProposalLifecycle.ACCEPTED_FOR_EXPORT,
        actor=reviewer,
    )
    execution = create_execution_plan(
        organization=organization,  # type: ignore[arg-type]
        proposal=proposal,
        image_digest=f"sha256:{'d' * 64}",
        actor=reviewer,
    )
    approve_execution_plan(
        organization=organization,  # type: ignore[arg-type]
        plan_public_id=execution.plan.public_id,
        actor=reviewer,
    )
    empty = SafeOutputV1.capture(b"", limit=65_536)
    execution_result = ExecutionResultV1(
        plan_sha256=execution.contract.plan_sha256,
        image=execution.contract.image,
        attempt=1,
        outcome=ExecutionOutcome.PASSED,
        elapsed_milliseconds=15,
        exit_code=0,
        stdout=empty,
        stderr=empty,
        timed_out=False,
        killed=False,
        cleanup_succeeded=True,
        isolation_checks=(("fixture_boundary", True),),
    )
    key = b"m10-result-signing-key-is-at-least-32-bytes"
    execution_run = record_execution_result(
        organization=organization,  # type: ignore[arg-type]
        plan_public_id=execution.plan.public_id,
        result=execution_result,
        result_signature=sign_payload(execution_result.canonical_bytes(), key=key),
        signing_key=key,
        idempotency_key=uuid.uuid4(),
    ).run

    differential = create_differential_plan(
        organization=organization,  # type: ignore[arg-type]
        execution_plan=execution.plan,
        candidate_variant="tax_regression",
        actor=reviewer,
    )
    repeated_plan = create_differential_plan(
        organization=organization,  # type: ignore[arg-type]
        execution_plan=execution.plan,
        candidate_variant="tax_regression",
        actor=reviewer,
    )
    assert differential.created is True
    assert repeated_plan.created is False
    assert differential.plan.pk == repeated_plan.plan.pk

    base = _observation(passed=True, total="113.00")
    candidate = _observation(passed=False, total="115.00")
    outcome, differences = compare_observations(base, candidate)
    result = DifferentialResultV1(
        plan_sha256=differential.contract.plan_sha256,
        image=differential.contract.image,
        attempt=1,
        base=base,
        candidate=candidate,
        outcome=outcome,
        differences=differences,
        mutations=(
            MutationResultV1("negative_guard_removed", MutationOutcome.SURVIVED, 10, 0),
            MutationResultV1("tax_rate_forced", MutationOutcome.KILLED, 11, 1),
        ),
        isolation_checks=(("fixture_boundary", True),),
        cleanup_succeeded=True,
    )
    wrong_mutation_order = replace(result, mutations=tuple(reversed(result.mutations)))
    with pytest.raises(ValueError, match="differential_result_mutation_binding_invalid"):
        record_differential_result(
            organization=organization,  # type: ignore[arg-type]
            plan_public_id=differential.plan.public_id,
            result=wrong_mutation_order,
            result_signature=sign_payload(wrong_mutation_order.canonical_bytes(), key=key),
            signing_key=key,
            idempotency_key=uuid.uuid4(),
        )
    idempotency_key = uuid.uuid4()
    recorded = record_differential_result(
        organization=organization,  # type: ignore[arg-type]
        plan_public_id=differential.plan.public_id,
        result=result,
        result_signature=sign_payload(result.canonical_bytes(), key=key),
        signing_key=key,
        idempotency_key=idempotency_key,
    )
    repeated = record_differential_result(
        organization=organization,  # type: ignore[arg-type]
        plan_public_id=differential.plan.public_id,
        result=result,
        result_signature=sign_payload(result.canonical_bytes(), key=key),
        signing_key=key,
        idempotency_key=idempotency_key,
    )
    assert recorded.created is True
    assert repeated.created is False
    assert recorded.run.outcome == "difference"
    assert recorded.run.mutation_killed == 1
    assert recorded.run.mutation_total == 2

    risk = RiskScore.objects.get(feature_set=feature_set)
    next_sequence = EvidenceItem.objects.filter(feature_set=feature_set).count()
    retrieval = EvidenceItem(
        organization=organization,
        snapshot=feature_set.snapshot,  # type: ignore[attr-defined]
        feature_set=feature_set,
        sequence=next_sequence,
        kind=EvidenceKind.RETRIEVAL,
        rule_id="m10.retrieval.fixture",
        title="Synthetic historical retrieval evidence",
        value={"status": "available"},
        reason="Fixture retrieval result is available for policy integration.",
        source_refs=["fixture:history:quote"],
        producer_version="m10-integration-fixture-v1",
        schema_version="releaseproof.retrieval-evidence.v1",
    )
    retrieval.full_clean()
    retrieval.save()
    risk_hold = risk.band == RiskBand.HIGH
    inputs = RecommendationInputsV1(
        model_risk=_available(
            "high" if risk_hold else "clear",
            f"risk_score:{risk.public_id}",
            hold=risk_hold,
        ),
        retrieval=_available("clear", f"evidence:{retrieval.public_id}"),
        generated_tests=_available("clear", f"generated_test_proposal:{proposal.public_id}"),
        execution=_available("clear", f"execution_run:{execution_run.public_id}"),
        differential=_available(
            "regression", f"differential_run:{recorded.run.public_id}", hold=True
        ),
        mutation=_available("survived", f"differential_run:{recorded.run.public_id}"),
        mutation_score_percent=50,
        llm_suggestion=Recommendation.SHIP,
    )
    recommendation = record_recommendation_decision(
        organization=organization,  # type: ignore[arg-type]
        differential_run=recorded.run,
        inputs=inputs,
        actor=reviewer,
    )
    duplicate_recommendation = record_recommendation_decision(
        organization=organization,  # type: ignore[arg-type]
        differential_run=recorded.run,
        inputs=inputs,
        actor=reviewer,
    )
    assert recommendation.created is True
    assert duplicate_recommendation.created is False
    assert recommendation.decision.recommendation == Recommendation.HOLD
    assert recommendation.decision.payload["decision"]["auto_merge"] is False

    table = connection.ops.quote_name(RecommendationDecision._meta.db_table)
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table} SET recommendation = %s WHERE id = %s",  # noqa: S608
            [Recommendation.SHIP, recommendation.decision.id],
        )
    other = factories.organization(name="M10 other", slug="m10-other")
    with pytest.raises(DatabaseError), transaction.atomic():
        DifferentialRun.objects.create(
            organization=other,
            plan=differential.plan,
            schema_version=result.schema_version,
            result_hash=result.result_sha256,
            attempt=2,
            outcome=result.outcome.value,
            mutation_killed=result.mutation_killed,
            mutation_total=result.mutation_total,
            idempotency_key=uuid.uuid4(),
            payload=result.as_dict(),
        )
