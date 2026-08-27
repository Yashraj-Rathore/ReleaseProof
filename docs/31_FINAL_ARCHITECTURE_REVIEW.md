# 31 — Final Architecture Review

Run after M16 only.

Return:
1. actual architecture diagram;
2. deviations from architecture/ADRs ranked Critical/High/Medium/Low;
3. dependency creep;
4. tenant/security/privacy findings;
5. sandbox findings/residual isolation assumptions;
6. data provenance/leakage/label-quality findings;
7. model/calibration/threshold findings;
8. RAG/LLM/agent evaluation findings;
9. ops/runbook gaps;
10. performance/cost evidence vs targets;
11. README/resume claim audit;
12. pilot-readiness decision;
13. staged correction queue, without auto-refactoring.

Allowed decision vocabulary: `READY_FOR_DEMO`, `READY_FOR_NARROW_PILOT`, `NOT_READY`.
Never say `PRODUCTION_READY` without a defined production environment, security/ops ownership, backups/recovery and deployment evidence.
