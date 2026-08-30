# 14 — Frontend and UX

## Stack
Semantic HTML5 + locally owned CSS + Django templates + HTMX + minimal vanilla JavaScript. Polished but intentionally not another SPA.

## Evidence-first questions
Every PR screen answers:
1. What changed?
2. What is the risk score/band and what artifact produced it?
3. Which evidence is deterministic, ML, retrieval, LLM or execution?
4. What is unavailable/unknown?
5. What should the human inspect next?

## Screens
### Repository dashboard
Installation/index status, recent PRs, current recommendation, analysis completeness, active model/evaluation versions.

### PR evidence
PR/base/head/stale state; recommendation; change/blast radius; model details; historical evidence; LLM hypotheses clearly labeled; generated tests; execution differentials; unknown/security states; analysis timeline.

### Model/evaluation
Active approved model, dataset manifest, split, metrics, threshold/calibration, comparison to prior artifact. Explicit “not measured” where missing.

### Policy/admin
GitHub installation, hosted LLM policy, retention, org-local learning opt-in, execution policy, quotas/budgets.

## Implemented M5 evidence views

The current-model page names the active artifact, candidate lifecycle/calibration states, evaluation
artifact and limitations. The snapshot-risk page names the exact active score artifact and renders
its deterministic rule contributions. Both are authenticated, active-organization scoped and say
that the score is not a calibrated probability; no color-only status or JavaScript is required.

## HTMX
Use for partial status refresh, evidence filtering, proposal approval, policy forms and evaluation detail. Server remains authoritative.

## Accessibility
Keyboard/focus/semantic landmarks, status not color-only, contrast, reduced motion, readable code/tables, mobile layout, no focus-stealing live regions.

## Demo seed
Fictional low-risk docs PR, risky auth PR, planted regression caught by execution, and LLM-unavailable graceful-degradation scenario.
