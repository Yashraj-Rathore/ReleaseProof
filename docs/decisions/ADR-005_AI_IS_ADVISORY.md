# ADR-005 — AI Is Advisory
**Status:** Accepted

ReleaseProof produces evidence and SHIP/REVIEW/HOLD/UNKNOWN recommendations but does not autonomously merge or deploy customer code. Generated tests are immutable drafts until a human accepts a revision for export. Acceptance does not authorize execution: M9 requires a separate audited Reviewer/Admin approval bound to the exact snapshot, proposal and execution-plan hashes. Human operators retain release authority. This is both a safety boundary and a product-trust decision.
