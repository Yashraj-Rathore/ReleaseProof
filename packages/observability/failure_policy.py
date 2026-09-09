"""Fail-closed dispositions exercised by the M14 operational drills."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FailureComponent(StrEnum):
    POSTGRESQL = "postgresql"
    REDIS = "redis"
    LLM_PROVIDER = "llm_provider"
    MODEL_ARTIFACT = "model_artifact"
    RETRIEVAL = "retrieval"
    CELERY_WORKER = "celery_worker"
    RUNNER = "runner"


class FailureDisposition(StrEnum):
    REJECT_REQUEST = "reject_request"
    RETAIN_AUTHORITATIVE_WORK = "retain_authoritative_work"
    PRESERVE_DETERMINISTIC_EVIDENCE = "preserve_deterministic_evidence"
    FALL_BACK_TO_BASELINE = "fall_back_to_baseline"
    FALL_BACK_TO_LEXICAL = "fall_back_to_lexical"
    MARK_JOB_FAILED = "mark_job_failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FailureDrill:
    component: FailureComponent
    injected_failure: str
    expected_disposition: FailureDisposition
    false_ship_possible: bool = False


def expected_failure_drills() -> tuple[FailureDrill, ...]:
    return (
        FailureDrill(
            FailureComponent.POSTGRESQL,
            "authoritative database unavailable",
            FailureDisposition.REJECT_REQUEST,
        ),
        FailureDrill(
            FailureComponent.REDIS,
            "outbox publisher unavailable",
            FailureDisposition.RETAIN_AUTHORITATIVE_WORK,
        ),
        FailureDrill(
            FailureComponent.LLM_PROVIDER,
            "hosted or local provider unavailable",
            FailureDisposition.PRESERVE_DETERMINISTIC_EVIDENCE,
        ),
        FailureDrill(
            FailureComponent.MODEL_ARTIFACT,
            "learned artifact missing or checksum-invalid",
            FailureDisposition.FALL_BACK_TO_BASELINE,
        ),
        FailureDrill(
            FailureComponent.RETRIEVAL,
            "semantic provider or reranker unavailable",
            FailureDisposition.FALL_BACK_TO_LEXICAL,
        ),
        FailureDrill(
            FailureComponent.CELERY_WORKER,
            "job input missing or permanently invalid",
            FailureDisposition.MARK_JOB_FAILED,
        ),
        FailureDrill(
            FailureComponent.RUNNER,
            "runner unavailable, timeout, or invalid result",
            FailureDisposition.UNKNOWN,
        ),
    )
