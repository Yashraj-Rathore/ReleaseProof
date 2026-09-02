"""Deterministic advisory recommendation fusion."""

from packages.recommendation_core.policy import (
    RECOMMENDATION_POLICY_VERSION,
    ComponentEvidence,
    ComponentStatus,
    Recommendation,
    RecommendationDecisionV1,
    RecommendationInputsV1,
    fuse_recommendation,
    recommendation_decision_from_dict,
    recommendation_inputs_from_dict,
)

__all__ = [
    "RECOMMENDATION_POLICY_VERSION",
    "ComponentEvidence",
    "ComponentStatus",
    "Recommendation",
    "RecommendationDecisionV1",
    "RecommendationInputsV1",
    "fuse_recommendation",
    "recommendation_decision_from_dict",
    "recommendation_inputs_from_dict",
]
