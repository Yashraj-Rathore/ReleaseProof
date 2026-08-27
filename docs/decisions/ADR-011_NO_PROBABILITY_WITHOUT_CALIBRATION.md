# ADR-011 — No Probability Claim Without Calibration
**Status:** Accepted

A model score is not labeled 'probability of failure' unless calibration quality is measured and acceptable on held-out data for the stated population. Otherwise the UI calls it a risk score or band. Confidence/uncertainty and UNKNOWN are explicit.
