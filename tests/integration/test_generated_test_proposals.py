from __future__ import annotations

import json
import uuid
from dataclasses import replace

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction

from adapters.llm import FakeLLMProvider
from adapters.test_generation.python_fixture import build_new_test_patch
from apps.web.analysis.llm_evidence import analyze_llm_evidence
from apps.web.analysis.models import AnalysisJob, OutboxEvent
from apps.web.audit.models import AuditLog
from apps.web.evidence.models import EvidenceItem
from apps.web.verification.models import (
    GeneratedTestProposal,
    ProposalLifecycle,
    ProposalLifecycleEvent,
)
from apps.web.verification.services import (
    ProposalWorkflowError,
    create_test_proposal,
    current_lifecycle,
    edit_test_proposal,
    export_test_proposal,
    transition_test_proposal,
)
from tests import factories
from tests.change_intel_fixtures import BASE_SHA
from tests.integration.test_llm_evidence_persistence import _local_policy, _scope
from tests.proposal_fixtures import VALID_TEST_PATH, proposal_fixture

pytestmark = pytest.mark.django_db


def _source(
    *,
    suffix: str,
    number: int,
    base_sha: str = BASE_SHA,
    head_sha: str | None = None,
) -> tuple[object, object, object, EvidenceItem]:
    organization, repository, feature_set = _scope(
        suffix=suffix,
        number=number,
        base_sha=base_sha,
        head_sha=head_sha,
    )
    _local_policy(organization, repository)
    deterministic = (
        EvidenceItem.objects.filter(feature_set=feature_set).order_by("sequence").first()
    )
    assert deterministic is not None
    result = analyze_llm_evidence(
        organization=organization,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        feature_set=feature_set,  # type: ignore[arg-type]
        provider=FakeLLMProvider(),
        provider_configuration=FakeLLMProvider.configuration,
        evidence_item_ids=(deterministic.public_id,),
    )
    assert result.status == "completed"
    return organization, repository, feature_set, result.evidence_item


def _proposal(source: EvidenceItem, **overrides: object) -> object:
    provider = source.value["provider"]
    prompt = source.value["prompt"]
    values: dict[str, object] = {
        "source_evidence_id": f"evidence:{source.public_id}",
        "evidence_ids": (source.source_refs[0],),
        "provider_name": provider["provider_name"],
        "model_id": provider["model_id"],
        "provider_adapter_version": provider["adapter_version"],
        "prompt_version": prompt["prompt_version"],
        "prompt_sha256": prompt["prompt_sha256"],
    }
    values.update(overrides)
    return proposal_fixture(**values)  # type: ignore[arg-type]


def test_create_is_idempotent_and_binds_safe_immutable_source_metadata() -> None:
    organization, _repository, _feature_set, source = _source(suffix="proposal", number=41)
    actor = factories.user(username="proposal-creator")
    contract = _proposal(source)

    first = create_test_proposal(
        organization=organization,  # type: ignore[arg-type]
        source_llm_evidence_public_id=source.public_id,
        proposal=contract,  # type: ignore[arg-type]
        actor=actor,
    )
    repeated = create_test_proposal(
        organization=organization,  # type: ignore[arg-type]
        source_llm_evidence_public_id=source.public_id,
        proposal=contract,  # type: ignore[arg-type]
        actor=actor,
    )

    assert first.created is True
    assert repeated.created is False
    assert repeated.proposal.pk == first.proposal.pk
    assert current_lifecycle(first.proposal) is ProposalLifecycle.DRAFT
    assert first.proposal.proposal_hash == contract.proposal_sha256  # type: ignore[attr-defined]
    assert first.proposal.validation_report["valid"] is True
    assert first.proposal.lifecycle_events.count() == 1
    audit = AuditLog.objects.get(resource_public_id=first.proposal.public_id)
    assert audit.metadata["proposal_hash"] == first.proposal.proposal_hash
    assert "patch" not in json.dumps(audit.metadata).lower()


def test_accept_export_and_edit_are_human_gated_without_execution_side_effects() -> None:
    organization, _repository, _feature_set, source = _source(suffix="workflow", number=42)
    reviewer = factories.user(username="proposal-reviewer")
    initial = create_test_proposal(
        organization=organization,  # type: ignore[arg-type]
        source_llm_evidence_public_id=source.public_id,
        proposal=_proposal(source),  # type: ignore[arg-type]
        actor=reviewer,
    ).proposal
    job_count = AnalysisJob.objects.count()
    outbox_count = OutboxEvent.objects.count()

    accepted = transition_test_proposal(
        organization=organization,  # type: ignore[arg-type]
        proposal_public_id=initial.public_id,
        target=ProposalLifecycle.ACCEPTED_FOR_EXPORT,
        actor=reviewer,
    )
    duplicate = transition_test_proposal(
        organization=organization,  # type: ignore[arg-type]
        proposal_public_id=initial.public_id,
        target=ProposalLifecycle.ACCEPTED_FOR_EXPORT,
        actor=reviewer,
    )
    exported = export_test_proposal(
        organization=organization,  # type: ignore[arg-type]
        proposal_public_id=initial.public_id,
        actor=reviewer,
    )

    assert accepted.created is True
    assert duplicate.created is False
    assert exported.patch == initial.patch
    assert current_lifecycle(initial) is ProposalLifecycle.ACCEPTED_FOR_EXPORT
    assert AnalysisJob.objects.count() == job_count
    assert OutboxEvent.objects.count() == outbox_count

    revised_content = (
        "from fixture_app.pricing import calculate_total\n\n\n"
        "def test_pricing_rounds_once_at_boundary() -> None:\n"
        "    assert calculate_total(200, 5) == 210\n"
    )
    replacement = replace(
        initial.as_contract(),
        target_behavior="Pricing remains stable at the documented boundary.",
        patch=build_new_test_patch(file_path=VALID_TEST_PATH, content=revised_content),
    )
    revised = edit_test_proposal(
        organization=organization,  # type: ignore[arg-type]
        proposal_public_id=initial.public_id,
        replacement=replacement,
        actor=reviewer,
    )

    assert revised.proposal.revision == 2
    assert revised.proposal.parent_proposal_id == initial.id
    assert revised.proposal.proposal_hash != initial.proposal_hash
    assert current_lifecycle(initial) is ProposalLifecycle.SUPERSEDED
    assert current_lifecycle(revised.proposal) is ProposalLifecycle.DRAFT
    with pytest.raises(ProposalWorkflowError, match="not_accepted"):
        export_test_proposal(
            organization=organization,  # type: ignore[arg-type]
            proposal_public_id=revised.proposal.public_id,
            actor=reviewer,
        )
    assert AnalysisJob.objects.count() == job_count
    assert OutboxEvent.objects.count() == outbox_count


def test_invalid_static_draft_is_visible_but_cannot_be_accepted_or_exported() -> None:
    organization, _repository, _feature_set, source = _source(suffix="invalid", number=43)
    reviewer = factories.user(username="invalid-reviewer")
    dangerous_content = "import os\n\n\ndef test_escape() -> None:\n    os.system('whoami')\n"
    invalid = _proposal(
        source,
        patch=build_new_test_patch(file_path=VALID_TEST_PATH, content=dangerous_content),
    )
    proposal = create_test_proposal(
        organization=organization,  # type: ignore[arg-type]
        source_llm_evidence_public_id=source.public_id,
        proposal=invalid,  # type: ignore[arg-type]
        actor=reviewer,
    ).proposal

    assert proposal.validation_report["valid"] is False
    assert any(
        check["code"] == "forbidden_capability_detected"
        for check in proposal.validation_report["checks"]
    )
    with pytest.raises(ProposalWorkflowError, match="invalid_proposal"):
        transition_test_proposal(
            organization=organization,  # type: ignore[arg-type]
            proposal_public_id=proposal.public_id,
            target=ProposalLifecycle.ACCEPTED_FOR_EXPORT,
            actor=reviewer,
        )
    with pytest.raises(DatabaseError), transaction.atomic():
        ProposalLifecycleEvent.objects.create(
            organization=organization,
            proposal=proposal,
            sequence=1,
            from_lifecycle=ProposalLifecycle.DRAFT,
            to_lifecycle=ProposalLifecycle.ACCEPTED_FOR_EXPORT,
            reason_code="bypass",
            actor=reviewer,
            correlation_id=uuid.uuid4(),
        )


def test_database_rejects_cross_tenant_binding_and_raw_mutation() -> None:
    organization_a, _repository_a, _feature_set_a, source_a = _source(suffix="tenant-a", number=44)
    organization_b, _repository_b, _feature_set_b, _source_b = _source(suffix="tenant-b", number=45)
    actor = factories.user(username="tenant-proposal-reviewer")
    contract = _proposal(source_a)
    validation = {
        "validator_version": "fixture",
        "valid": True,
        "content_sha256": "a" * 64,
        "checks": [{"name": "fixture", "passed": True, "code": "fixture"}],
    }

    with pytest.raises(IntegrityError), transaction.atomic():
        GeneratedTestProposal.objects.create(
            organization=organization_b,
            source_llm_evidence=source_a,
            proposal_group_id=uuid.uuid4(),
            revision=1,
            schema_version=contract.schema_version,  # type: ignore[attr-defined]
            proposal_hash=contract.proposal_sha256,  # type: ignore[attr-defined]
            target_behavior=contract.target_behavior,  # type: ignore[attr-defined]
            rationale=contract.rationale,  # type: ignore[attr-defined]
            evidence_ids=list(contract.evidence_ids),  # type: ignore[attr-defined]
            file_path=contract.file_path,  # type: ignore[attr-defined]
            patch=contract.patch,  # type: ignore[attr-defined]
            commands=list(contract.commands),  # type: ignore[attr-defined]
            expected_result=contract.expected_result,  # type: ignore[attr-defined]
            risk=contract.risk.value,  # type: ignore[attr-defined]
            test_adapter=contract.test_adapter,  # type: ignore[attr-defined]
            test_adapter_version=contract.test_adapter_version,  # type: ignore[attr-defined]
            generation_metadata=contract.generation.as_dict(),  # type: ignore[attr-defined]
            validation_report=validation,
            created_by=actor,
        )

    proposal = create_test_proposal(
        organization=organization_a,  # type: ignore[arg-type]
        source_llm_evidence_public_id=source_a.public_id,
        proposal=contract,  # type: ignore[arg-type]
        actor=actor,
    ).proposal
    table = connection.ops.quote_name(GeneratedTestProposal._meta.db_table)
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table} SET revision = %s WHERE id = %s",  # noqa: S608
            [99, proposal.id],
        )
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM {table} WHERE id = %s",  # noqa: S608
            [proposal.id],
        )
