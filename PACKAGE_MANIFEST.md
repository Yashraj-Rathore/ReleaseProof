# Package Manifest

ReleaseProof uses source-of-truth numbered docs, explicit ADRs, issue-level acceptance criteria,
a generated single-file master specification, and one Codex milestone at a time.

## Root

- `README.md`
- `AGENTS.md`
- `CODEX_START_HERE.md`
- `CODEX_PROMPT_SEQUENCE.md`
- `CODEX_MASTER_IMPLEMENTATION_SPEC.md`
- `IMPLEMENTATION_CHECKLIST.md`
- `PROJECT_STATUS.md`
- `CHANGELOG.md`
- `pyproject.toml`, `uv.lock`, `.python-version`
- `compose.yaml`, `.env.example`

## Implemented M1 folders

- `apps/web/` — Django project plus the canonical ten modular apps.
- `packages/` — framework-light domain and future algorithm boundaries.
- `adapters/` — deterministic provider fakes and the bounded S3 implementation.
- `workers/` — Celery worker package; domain task behavior remains milestone-owned.
- `tests/` — unit/web tests, the SeaweedFS contract test, and licensed synthetic fixture.
- `deploy/` — PostgreSQL extension bootstrap and local-only SeaweedFS S3 configuration.
- `eng/` — local config, validation, fake/object-store smoke, bootstrap, and spec synchronization.
- `docs/` — numbered source-of-truth specifications.
- `docs/decisions/` — ADRs.
- `codex-prompts/` — one prompt per milestone.
- `templates/` — DoD, dataset/model/experiment/security/pilot templates.
- `notebooks/`, `datasets/` — guarded placeholders for their owning milestones.

## Repository shape

```text
apps/
  web/                 # Django control plane with the ten RP-0003 apps
packages/
  domain/
  github_contracts/
  change_intel/
  dataset_core/
  ml_core/
  retrieval_core/
  ai_core/
  agent_core/
  execution_contracts/
  observability/
workers/
adapters/              # provider implementations and deterministic fakes
notebooks/
datasets/
tests/
deploy/
docs/
codex-prompts/
templates/
```

M1 creates declared package boundaries but leaves milestone-owned algorithms empty. FastAPI model
serving and the runner trust boundary remain absent until their explicit gates. The canonical
Django apps are `identity`, `organizations`, `repositories`, `changes`, `evidence`, `risk`,
`retrieval`, `analysis`, `verification`, and `audit`. Policy records remain owned by organizations
and repositories until a later assigned issue justifies a separate module.
