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

M3 implements `change-features-v1` as the shared prediction-time definition source. Each persisted
row records extractor/schema versions, per-feature provenance, missingness and a content hash.
Repository history is filtered strictly before the snapshot prediction timestamp; future rows are
excluded in the pure extractor and cannot enter the tenant-scoped persistence query. Author keys,
check outcomes and later labels are not predictors: only pre-change aggregate familiarity and
explicit historical check-failure proxy counts are materialized. M4 still owns dataset labels,
split assignment, materialization and evaluated baseline artifacts.

## Data quality report
Missingness, class balance, duplicates, split counts, feature distributions, label ambiguity, drift vs previous compatible dataset, leakage checks.

Large/raw/private data stays out of Git; manifests/small safe fixtures live in Git and large artifacts are content-addressed in object storage.

## Implemented M4 contracts and evidence

- Admission `source-admission-v1` captures numeric repository identity, canonical source, SPDX and
  license-evidence hash/version, terms URL/review date, acquisition method, allowed fields and
  artifacts, redistribution/retention/attribution limits, `as_of`, observation window, reviewer,
  record/rate bounds and synthetic/approval status. The extractor has no HTTP client; public input
  without a complete approved API admission fails closed.
- Label rule `proxy-label-rule-v1` separately represents explicit revert, hotfix, rapid follow-up,
  required-check failure, no-proxy-observed and ambiguous outcomes. Positives are not called
  incidents. A negative requires an observation exactly closing the complete window; ambiguous,
  missing, late or incomplete evidence stays unknown and is excluded.
- Split rule `temporal-split-v1` uses frozen half-open timestamps. The one-repository fixture cannot
  support a repository holdout, which is recorded as a limitation. M5 must not reinterpret or
  mutate the committed assignments.
- Leakage report `leakage-report-v1` fails on cross-split head SHA, exact diff or normalized
  near-duplicate fingerprints; incompatible feature schema; label/outcome/identity predictors;
  unknown included rows; invalid temporal assignment; or unavailable observation time.
- Materialization `feature-materialization-v1` invokes the same `change-features-v1` extractor used
  by product analysis and records feature values, missingness, provenance and hashes per immutable
  snapshot. Outcome fields are joined only after prediction-time feature extraction.
- Dataset `releaseproof-m4-synthetic-v1` contains 16 synthetic rows: 6 train, 4 validation, 4 test
  and 2 excluded unknowns; the 14 included rows have seven positive and seven negative proxies.
  These balanced fixture counts are designed test data, not an estimate of real prevalence.
- `tests/golden/m4_synthetic_baseline_v1.json` is the raw reproducible manifest, feature-row,
  split/leakage and baseline-evaluation artifact. Its manifest names extraction code commit
  `3448b1f879682d2b12a212d4c82d8fee87e33a12`; the repository validator rebuilds it byte-for-byte.

## M5 reuse

M5 does not mutate the manifest, rows, labels or split assignments. Train-only preprocessing fits
explicit nullable-feature imputation, missingness indicators and scaling on the six training rows;
validation selects configurations/thresholds, and the four test rows are read only after the
experiment declaration is frozen. The resulting artifact names the exact M4 manifest/split hashes.
