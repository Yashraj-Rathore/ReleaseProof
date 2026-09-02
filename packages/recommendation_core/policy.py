"""Evaluable M10 policy: evidence may strengthen caution but never authorize a merge."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from packages.execution_contracts.contracts import object_sha256

RECOMMENDATION_POLICY_VERSION = "recommendation-fusion-v1"
MUTATION_REVIEW_THRESHOLD_PERCENT = 50
_MANDATORY = ("model_risk", "retrieval", "generated_tests", "execution", "differential", "mutation")


class Recommendation(StrEnum):
    SHIP = "SHIP"
    REVIEW = "REVIEW"
    HOLD = "HOLD"
    UNKNOWN = "UNKNOWN"


class ComponentStatus(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ComponentEvidence:
    status: ComponentStatus
    fact: str
    evidence_ids: tuple[str, ...]
    deterministic_hold: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.status, ComponentStatus)
            or not isinstance(self.fact, str)
            or not 1 <= len(self.fact) <= 128
            or type(self.deterministic_hold) is not bool
        ):
            raise ValueError("component evidence is invalid")
        if (
            len(self.evidence_ids) > 32
            or len(set(self.evidence_ids)) != len(self.evidence_ids)
            or not all(
                isinstance(item, str) and 1 <= len(item) <= 192 and item.isascii()
                for item in self.evidence_ids
            )
        ):
            raise ValueError("component evidence IDs are invalid")
        if self.status is not ComponentStatus.AVAILABLE and self.deterministic_hold:
            raise ValueError("unavailable evidence cannot assert a deterministic hold")

    def as_dict(self) -> dict[str, object]:
        return {
            "deterministic_hold": self.deterministic_hold,
            "evidence_ids": list(self.evidence_ids),
            "fact": self.fact,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class RecommendationInputsV1:
    model_risk: ComponentEvidence
    retrieval: ComponentEvidence
    generated_tests: ComponentEvidence
    execution: ComponentEvidence
    differential: ComponentEvidence
    mutation: ComponentEvidence
    mutation_score_percent: int | None
    llm_suggestion: Recommendation | None = None

    def __post_init__(self) -> None:
        if self.mutation_score_percent is not None and (
            type(self.mutation_score_percent) is not int
            or not 0 <= self.mutation_score_percent <= 100
        ):
            raise ValueError("mutation score is invalid")
        if (
            self.mutation.status is ComponentStatus.AVAILABLE
            and self.mutation_score_percent is None
        ):
            raise ValueError("available mutation evidence requires a score")
        if self.llm_suggestion is not None and not isinstance(self.llm_suggestion, Recommendation):
            raise ValueError("LLM suggestion is invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            **{name: getattr(self, name).as_dict() for name in _MANDATORY},
            "llm_suggestion": self.llm_suggestion.value if self.llm_suggestion else None,
            "mutation_score_percent": self.mutation_score_percent,
        }


@dataclass(frozen=True, slots=True)
class RecommendationDecisionV1:
    recommendation: Recommendation
    reason_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    inputs_sha256: str
    policy_version: str = RECOMMENDATION_POLICY_VERSION
    advisory_only: bool = True
    auto_merge: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.recommendation, Recommendation):
            raise ValueError("recommendation is invalid")
        if self.policy_version != RECOMMENDATION_POLICY_VERSION:
            raise ValueError("recommendation policy version is unsupported")
        if not self.advisory_only or self.auto_merge:
            raise ValueError("recommendation cannot authorize merge or deploy")
        if (
            not isinstance(self.inputs_sha256, str)
            or len(self.inputs_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.inputs_sha256)
        ):
            raise ValueError("recommendation input hash is invalid")
        if (
            not self.reason_codes
            or len(self.reason_codes) > 16
            or len(set(self.reason_codes)) != len(self.reason_codes)
            or not all(
                isinstance(item, str) and 1 <= len(item) <= 128 and item.isascii()
                for item in self.reason_codes
            )
            or len(self.evidence_ids) > 192
            or len(set(self.evidence_ids)) != len(self.evidence_ids)
        ):
            raise ValueError("recommendation evidence or reasons are invalid")

    def content_dict(self) -> dict[str, object]:
        return {
            "advisory_only": self.advisory_only,
            "auto_merge": self.auto_merge,
            "evidence_ids": list(self.evidence_ids),
            "inputs_sha256": self.inputs_sha256,
            "policy_version": self.policy_version,
            "reason_codes": list(self.reason_codes),
            "recommendation": self.recommendation.value,
        }

    @property
    def decision_sha256(self) -> str:
        return object_sha256(self.content_dict())

    def as_dict(self) -> dict[str, object]:
        return {**self.content_dict(), "decision_sha256": self.decision_sha256}


def recommendation_inputs_from_dict(value: object) -> RecommendationInputsV1:
    if not isinstance(value, dict) or set(value) != {
        *_MANDATORY,
        "llm_suggestion",
        "mutation_score_percent",
    }:
        raise ValueError("recommendation inputs schema is invalid")

    def component(name: str) -> ComponentEvidence:
        item = value[name]
        if not isinstance(item, dict) or set(item) != {
            "deterministic_hold",
            "evidence_ids",
            "fact",
            "status",
        }:
            raise ValueError("recommendation component schema is invalid")
        return ComponentEvidence(
            status=ComponentStatus(item["status"]),
            fact=item["fact"],
            evidence_ids=tuple(item["evidence_ids"]),
            deterministic_hold=item["deterministic_hold"],
        )

    try:
        suggestion = value["llm_suggestion"]
        return RecommendationInputsV1(
            **{name: component(name) for name in _MANDATORY},
            mutation_score_percent=value["mutation_score_percent"],
            llm_suggestion=Recommendation(suggestion) if suggestion is not None else None,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("recommendation inputs schema is invalid") from error


def recommendation_decision_from_dict(value: object) -> RecommendationDecisionV1:
    if not isinstance(value, dict) or set(value) != {
        "advisory_only",
        "auto_merge",
        "decision_sha256",
        "evidence_ids",
        "inputs_sha256",
        "policy_version",
        "reason_codes",
        "recommendation",
    }:
        raise ValueError("recommendation decision schema is invalid")
    try:
        supplied_hash = value["decision_sha256"]
        decision = RecommendationDecisionV1(
            recommendation=Recommendation(value["recommendation"]),
            reason_codes=tuple(value["reason_codes"]),
            evidence_ids=tuple(value["evidence_ids"]),
            inputs_sha256=value["inputs_sha256"],
            policy_version=value["policy_version"],
            advisory_only=value["advisory_only"],
            auto_merge=value["auto_merge"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("recommendation decision schema is invalid") from error
    if supplied_hash != decision.decision_sha256:
        raise ValueError("recommendation decision hash mismatch")
    return decision


def fuse_recommendation(inputs: RecommendationInputsV1) -> RecommendationDecisionV1:
    """Apply precedence HOLD > UNKNOWN > REVIEW > SHIP; LLM suggestions are never decisive."""

    components = {name: getattr(inputs, name) for name in _MANDATORY}
    evidence_ids = tuple(
        sorted(
            {
                identifier
                for component in components.values()
                for identifier in component.evidence_ids
            }
        )
    )
    holds = tuple(
        f"{name}_deterministic_hold"
        for name, component in components.items()
        if component.deterministic_hold
    )
    if holds:
        recommendation = Recommendation.HOLD
        reasons = holds
    else:
        unavailable = tuple(
            f"{name}_{component.status.value}"
            for name, component in components.items()
            if component.status is not ComponentStatus.AVAILABLE
        )
        if unavailable:
            recommendation = Recommendation.UNKNOWN
            reasons = unavailable
        elif (
            inputs.mutation_score_percent is not None
            and inputs.mutation_score_percent < MUTATION_REVIEW_THRESHOLD_PERCENT
        ):
            recommendation = Recommendation.REVIEW
            reasons = ("mutation_score_below_review_threshold",)
        elif any(
            component.fact in {"review", "warning", "survived"} for component in components.values()
        ):
            recommendation = Recommendation.REVIEW
            reasons = ("available_evidence_requires_human_review",)
        else:
            recommendation = Recommendation.SHIP
            reasons = ("all_mandatory_evidence_clear",)
    return RecommendationDecisionV1(
        recommendation=recommendation,
        reason_codes=reasons,
        evidence_ids=evidence_ids,
        inputs_sha256=object_sha256(inputs.as_dict()),
    )
