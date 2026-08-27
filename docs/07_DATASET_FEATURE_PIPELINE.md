# 07 — Dataset and Feature Pipeline

## Core credibility problem
Fitting XGBoost is easy; trustworthy labels are not. Reverts, hotfixes and follow-up fixes are noisy **proxies**, not proof that a PR caused a production incident.

## Data phases

### A — Synthetic fixture
Only for UI/demo/tests. `synthetic=true`. Never mixed invisibly into real performance claims.

### B — Curated public-repository proxy dataset
Explicit allowlist of public repositories; use approved APIs/rate limits and record source/license/usage notes. Potential positive proxies are separately labeled:
- explicit revert
- linked rapid follow-up fix under a documented rule
- repository-maintainer hotfix/revert labels where reliable
Unknown remains unknown when observation/history is incomplete.

### Public-source admission gate
No public repository is extracted until an approval record captures repository numeric identity and canonical URL, SPDX/license evidence and version, hosting/API terms URL and review date, permitted acquisition method, allowed fields/artifacts, redistribution/retention limits, attribution requirements, analysis `as_of` cutoff, required outcome-observation window, and reviewer. Missing or incompatible license/terms evidence excludes the source. Robots.txt, rate limits and provider deletion events are respected; public visibility alone is not permission to build or redistribute a dataset.

### C — Organization-local outcomes
Explicit opt-in only. May include rollback/hotfix/incident/manual reviewer labels. Isolated by organization unless future explicit agreement says otherwise.

## Manifest
Every dataset version records:
- manifest/hash
- extraction code commit
- source repos + observation windows
- per-source approval record + license/terms evidence hash
- label-rule version
- exclusions
- counts/class balance/unknowns
- feature schema
- split rule
- usage/license notes
- synthetic flag
- known label weaknesses

## Leakage controls
Headline evaluation uses temporal and/or repository holdout; both preferred when data permits.
Automated checks:
- no same head SHA across splits
- no duplicate diff hash across splits
- no outcome-derived predictor
- only information available at prediction time
- no default author identity/employee scoring feature
- fixed published train/val/test assignments
- observation window complete before split assignment; incomplete rows remain unknown rather than negative

## Train/serve consistency
Raw immutable snapshot -> deterministic feature extractor -> normalized feature table. Training and inference import the same feature definitions/version.

## Data quality report
Missingness, class balance, duplicates, split counts, feature distributions, label ambiguity, drift vs previous compatible dataset, leakage checks.

Large/raw/private data stays out of Git; manifests/small safe fixtures live in Git and large artifacts are content-addressed in object storage.
