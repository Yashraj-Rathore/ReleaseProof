"""Auditable proxy-label rules; proxy outcomes are never called incidents."""

from __future__ import annotations

from datetime import timedelta

from packages.dataset_core.contracts import (
    LABEL_RULE_VERSION,
    ExtractedSnapshot,
    LabelAssignment,
    ProxyLabel,
    ProxyOutcomeKind,
    SourceAdmission,
)

_POSITIVE_KINDS = {
    ProxyOutcomeKind.EXPLICIT_REVERT,
    ProxyOutcomeKind.HOTFIX,
    ProxyOutcomeKind.RAPID_FOLLOWUP_FIX,
    ProxyOutcomeKind.FAILED_REQUIRED_CHECK,
}

KNOWN_LABEL_WEAKNESSES = (
    "A revert, hotfix, rapid follow-up fix or required-check failure is a proxy, "
    "not proof of a production incident.",
    "No observed proxy after a complete window is not proof that a change was defect-free.",
    "Repository practices affect which proxy outcomes are recorded and can bias comparisons.",
    "The synthetic fixture measures pipeline behavior only and cannot estimate customer "
    "performance.",
)


def assign_proxy_label(
    snapshot: ExtractedSnapshot,
    *,
    admission: SourceAdmission,
) -> LabelAssignment:
    window_end = snapshot.prediction_time + timedelta(days=admission.observation_window_days)
    if window_end > admission.as_of:
        return LabelAssignment(
            label=ProxyLabel.UNKNOWN,
            rule_id=f"{LABEL_RULE_VERSION}.incomplete_window",
            reason=(
                "Required outcome-observation window was incomplete at the admitted as_of cutoff."
            ),
            outcome_kind=snapshot.outcome.kind if snapshot.outcome else None,
            observed_at=snapshot.outcome.observed_at if snapshot.outcome else None,
            evidence_refs=snapshot.outcome.evidence_refs if snapshot.outcome else (),
        )
    if snapshot.outcome is None:
        return LabelAssignment(
            label=ProxyLabel.UNKNOWN,
            rule_id=f"{LABEL_RULE_VERSION}.missing_outcome",
            reason="No auditable proxy-outcome observation was supplied.",
            outcome_kind=None,
            observed_at=None,
            evidence_refs=(),
        )
    outcome = snapshot.outcome
    if outcome.kind is ProxyOutcomeKind.AMBIGUOUS:
        return LabelAssignment(
            label=ProxyLabel.UNKNOWN,
            rule_id=f"{LABEL_RULE_VERSION}.ambiguous",
            reason="Outcome evidence was explicitly ambiguous and remains unknown.",
            outcome_kind=outcome.kind,
            observed_at=outcome.observed_at,
            evidence_refs=outcome.evidence_refs,
        )
    if outcome.observed_at is None:
        return LabelAssignment(
            label=ProxyLabel.UNKNOWN,
            rule_id=f"{LABEL_RULE_VERSION}.missing_observation_time",
            reason="Outcome evidence lacked an observation timestamp.",
            outcome_kind=outcome.kind,
            observed_at=None,
            evidence_refs=outcome.evidence_refs,
        )
    if outcome.observed_at < snapshot.prediction_time:
        raise ValueError("outcome observation predates the prediction timestamp")
    if outcome.observed_at > admission.as_of:
        raise ValueError("outcome observation exceeds the admitted as_of cutoff")
    if outcome.observed_at > window_end:
        return LabelAssignment(
            label=ProxyLabel.UNKNOWN,
            rule_id=f"{LABEL_RULE_VERSION}.outside_window",
            reason="Outcome evidence occurred after the declared observation window.",
            outcome_kind=outcome.kind,
            observed_at=outcome.observed_at,
            evidence_refs=outcome.evidence_refs,
        )
    if outcome.kind in _POSITIVE_KINDS:
        return LabelAssignment(
            label=ProxyLabel.POSITIVE,
            rule_id=f"{LABEL_RULE_VERSION}.{outcome.kind}",
            reason=(
                f"Observed {outcome.kind.value} within the complete proxy window; this is not an "
                "incident label."
            ),
            outcome_kind=outcome.kind,
            observed_at=outcome.observed_at,
            evidence_refs=outcome.evidence_refs,
        )
    if outcome.kind is ProxyOutcomeKind.NO_PROXY_OBSERVED:
        if outcome.observed_at != window_end:
            raise ValueError(
                "negative proxy observation must close the complete observation window"
            )
        return LabelAssignment(
            label=ProxyLabel.NEGATIVE,
            rule_id=f"{LABEL_RULE_VERSION}.no_proxy_observed",
            reason=(
                "No configured positive proxy was observed during the complete window; this is not "
                "proof of safety."
            ),
            outcome_kind=outcome.kind,
            observed_at=outcome.observed_at,
            evidence_refs=outcome.evidence_refs,
        )
    raise ValueError("outcome kind is not handled by proxy-label rule v1")
