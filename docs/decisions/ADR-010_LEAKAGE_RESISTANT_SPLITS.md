# ADR-010 — Leakage-Resistant Evaluation Splits
**Status:** Accepted

Formal ML evaluation uses repository-grouped and/or temporal boundaries appropriate to the research question. Feature computation uses only information available at prediction time. Duplicate/near-duplicate changes and future outcomes cannot cross train/test boundaries. Split manifests are immutable and reviewed before results are publicized.
