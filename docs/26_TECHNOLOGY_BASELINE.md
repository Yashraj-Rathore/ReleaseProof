# 26 — Technology Baseline — foundation verified 2026-08-27; M5 verified 2026-08-30; M6 verified 2026-08-31; M7/M8 verified 2026-09-01

This is the dated Prompt 0 decision. Prompt 1 uses the exact foundation pins below. Later ML/AI/serving packages are compatibility snapshots, not permission to install them early; their exact pins are reverified and locked only when the owning milestone begins.

## Runtime decision

Use CPython **3.13.15**. It is the conservative intersection of Django 6.1 (Python 3.12–3.14), Celery 5.6 (through Python 3.13), the selected ML stack and the optional vLLM path (Python 3.10–3.13). Python 3.14 is deliberately not selected for the foundation.

Evidence: [Python 3.13.15](https://www.python.org/downloads/release/python-31315/), [Django 6.1 compatibility](https://docs.djangoproject.com/en/6.1/faq/install/), [Celery 5.6 compatibility](https://docs.celeryq.dev/en/main/history/whatsnew-5.6.html), [vLLM requirements](https://docs.vllm.ai/en/latest/getting_started/quickstart/).

## Prompt 1 pins

| Technology | Exact pin | Rationale / official evidence |
|---|---:|---|
| CPython | `3.13.15` | Conservative full-stack intersection; see runtime decision. |
| uv | `0.12.6` | One lock/install workflow. [Changelog](https://github.com/astral-sh/uv/blob/main/CHANGELOG.md?plain=1) |
| Django | `6.1` | Current supported stable, compatible with Python 3.13 and PostgreSQL 18. [Release notes](https://docs.djangoproject.com/en/6.1/releases/6.1/) |
| Django REST Framework | `3.18.0` | Adds Django 6.1 support. [Release notes](https://www.django-rest-framework.org/community/release-notes/) |
| psycopg | `3.3.4` | PostgreSQL driver required by Django. [Release history](https://pypi.org/project/psycopg/) |
| Celery | `5.6.3` | Current stable 5.6 patch, compatible with Python 3.13. [Changelog](https://docs.celeryq.dev/en/stable/changelog.html) |
| Boto3 | `1.43.81` | AWS-maintained Python SDK used only in the S3 adapter for ADR-016's bounded object-store contract; supports Python 3.13. [PyPI release](https://pypi.org/project/boto3/1.43.81/) |
| HTMX | `2.0.10` | Vendor the exact minified asset and checksum; do not require Node or a CDN. [Changelog](https://github.com/bigskysoftware/htmx/blob/master/CHANGELOG.md) |
| PostgreSQL | `18.6` | Current patched PostgreSQL 18 line. [Documentation](https://www.postgresql.org/docs/18/) |
| pgvector | `0.8.6` | Compatible with PostgreSQL 18. Use `pgvector/pgvector:0.8.6-pg18-trixie` plus resolved manifest digest. [Changelog](https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md?plain=1) |
| Redis | `8.10.1` | Current security-fixed 8.10 patch. Use an exact image tag plus digest. [Release notes](https://redis.io/docs/latest/operate/oss_and_stack/stack-with-enterprise/release-notes/redisce/redisos-8.10-release-notes/) |
| SeaweedFS | `4.44` | Maintained Apache-2.0 S3-compatible local store selected by ADR-016. Use `chrislusf/seaweedfs:4.44` plus resolved manifest digest. [Release](https://github.com/seaweedfs/seaweedfs/releases/tag/4.44) |
| Docker Engine | `29.7.2` | Verified host/container baseline. [Release notes](https://docs.docker.com/engine/release-notes/29/) |
| Docker Compose | `5.4.0` | Verified Compose plugin baseline. [Releases](https://github.com/docker/compose/releases/tag/v5.4.0) |

MinIO is explicitly excluded: its open-source repository was archived on 2026-04-25 and is not a supported security baseline. Do not silently reintroduce it. SeaweedFS compatibility is limited to the ReleaseProof contract tests in ADR-016; no complete-S3-equivalence claim is made.

## Prompt 1 development/test pins

| Technology | Exact pin | Activation |
|---|---:|---|
| pytest | `9.1.1` | M1 |
| pytest-django | `4.14.0` | M1 |
| Ruff | `0.16.4` | M1 |
| mypy | `2.3.0` | M1 |
| django-stubs | `6.1.0` | M1 |
| pre-commit | `4.6.2` | M1 |
| Testcontainers Python | `4.15.0` | M1 where it adds isolation beyond Compose tests |
| Playwright Python | `1.62.0` | Package may be locked in M1; browser download and E2E activation start in M2 |
| pytest-playwright | `0.9.0` | M2 |

Evidence: [pytest](https://docs.pytest.org/en/stable/changelog.html), [pytest-django](https://pytest-django.readthedocs.io/en/stable/), [Ruff](https://github.com/astral-sh/ruff/releases), [mypy](https://mypy-lang.org/news.html), [django-stubs](https://pypi.org/project/django-stubs/), [pre-commit](https://pypi.org/project/pre-commit/), [Playwright](https://playwright.dev/python/docs/release-notes), [Testcontainers](https://github.com/testcontainers/testcontainers-python/releases).

Python `unittest`, HTML5, CSS, minimal browser JavaScript, PostgreSQL JSONB and PostgreSQL FTS do not have independent package pins. The first FTS configuration is specified in docs/10. No Node package manager is introduced.

## Later milestone compatibility snapshot

Do not add these to the Prompt 1 lock solely because they appear here.

| Technology | Verified snapshot | Owning gate |
|---|---:|---|
| NumPy | `2.5.2` | Locked by M5; see the verified M5 table below |
| pandas | `3.0.5` | Locked by M5; see the verified M5 table below |
| scikit-learn | `1.9.0` | Locked by M5; see the verified M5 table below |
| XGBoost | `3.4.1` | Locked by M5 as the CPU distribution; see below |
| PyTorch | `2.13.0`, CPU build first | M11 reverify against hardware/runtime |
| Transformers | `5.15.1` | M11 reverify with PyTorch |
| sentence-transformers | `6.0.0` | M6/M11 reverify |
| LangChain core | `1.6.0` | M7 only if the adapter needs it |
| LangChain OpenAI | `1.6.0` | M7 only if it reduces contract code |
| LangGraph | `1.2.11` | M12 |
| MLflow | `3.15.1` | M13 |
| OpenTelemetry API/SDK | `1.44.0` | M14 |
| OpenTelemetry instrumentation | `0.65b0` | M14; beta versioning is explicit |
| FastAPI | `0.141.1` | M15 only if RP-1402 returns `EXTRACT_FASTAPI` |
| Ollama | `0.32.11` | Optional M15 adapter |
| vLLM | `0.26.0` | Optional M15 Linux/GPU path |

Official compatibility/release evidence: [NumPy](https://numpy.org/news/), [pandas](https://pandas.pydata.org/docs/whatsnew/), [scikit-learn](https://scikit-learn.org/stable/whats_new.html), [XGBoost](https://xgboost.readthedocs.io/en/stable/changes/index.html), [PyTorch](https://github.com/pytorch/pytorch/blob/main/RELEASE.md), [Transformers](https://huggingface.co/docs/transformers/installation), [sentence-transformers](https://sbert.net/docs/installation.html), [LangChain](https://docs.langchain.com/oss/python/versioning), [MLflow](https://mlflow.org/releases/), [OpenTelemetry](https://github.com/open-telemetry/opentelemetry-python/releases), [FastAPI](https://fastapi.tiangolo.com/deployment/versions/), [Ollama](https://github.com/ollama/ollama/releases), [vLLM](https://github.com/vllm-project/vllm/releases).

The OpenAI Python SDK was milestone-resolved by RP-0602 and is recorded in the verified M7 table
below. The earlier compatibility snapshot intentionally had no speculative SDK pin.

## M5 classical-ML pins — verified and locked 2026-08-30

These four direct packages live in the separate `ml` dependency group. CPython remains 3.13.15;
the exact lock resolved SciPy 1.18.1, joblib 1.5.3, narwhals 2.25.0 and threadpoolctl 3.6.0 as
transitive requirements. pandas is used for the explicit ordered tabular preprocessing boundary,
NumPy for numeric matrices/artifacts, scikit-learn for logistic regression/metrics and XGBoost for
the tree candidate. No notebook, SHAP, GPU or model-serving dependency is added.

| Package | Exact pin | Official compatibility/release evidence |
|---|---:|---|
| NumPy | `2.5.2` | The official [2.5.2 release notes](https://numpy.org/devdocs/release/2.5.2-notes.html) identify it as the 2026-08-09 patch and support Python 3.12–3.15, including the selected 3.13. |
| pandas | `3.0.5` | The official [3.0.5 release notes](https://pandas.pydata.org/docs/whatsnew/v3.0.5.html) identify the 2026-07-22 patch; the pandas [3.0.5 release](https://github.com/pandas-dev/pandas/releases/tag/v3.0.5) supports Python 3.11+, and its [install guide](https://pandas.pydata.org/docs/getting_started/install.html) requires NumPy at least 1.26.0. |
| scikit-learn | `1.9.0` | The official [1.9.0 release notes](https://scikit-learn.org/stable/whats_new/v1.9.html) identify the June 2026 stable release; its [tagged project metadata](https://github.com/scikit-learn/scikit-learn/blob/1.9.0/pyproject.toml) requires Python 3.11+ and includes Python 3.13, while the official [install guide](https://scikit-learn.org/stable/install.html) lists its NumPy/SciPy/joblib/narwhals/threadpoolctl requirements. |
| XGBoost CPU | `xgboost-cpu==3.4.1` | The official [3.4.1 notes](https://xgboost.readthedocs.io/en/stable/changes/v3.4.0.html) identify the 2026-08-14 patch; 3.3 raised the [minimum Python version to 3.12](https://xgboost.readthedocs.io/en/stable/changes/v3.3.0.html), and the [install guide](https://xgboost.readthedocs.io/en/stable/install.html#minimal-installation-cpu-only) documents the smaller CPU-only distribution. Python 3.13 is inside that supported range. |

`uv sync --frozen --group dev --group ml` installed these exact pins together on CPython 3.13.15,
and M5 training/inference/serialization tests passed. That repository result is compatibility
evidence for this locked ReleaseProof environment, not a universal platform claim.

## M6 retrieval pins — verified and locked 2026-08-31

| Package/artifact | Exact pin | Official evidence / use |
|---|---:|---|
| pgvector Python | `0.5.0` | The official [pgvector-python project](https://github.com/pgvector/pgvector-python) documents Django `VectorField`, distance expressions and HNSW indexes; its project metadata requires Python 3.10+. This is the Django adapter for the already pinned pgvector PostgreSQL extension. |
| sentence-transformers | `6.0.0` | The official [PyPI release](https://pypi.org/project/sentence-transformers/6.0.0/) is stable, supports Python 3.13 and documents both `SentenceTransformer` and `CrossEncoder`. It is isolated in the optional `semantic` group; normal CI/test paths do not download model weights. |
| embedding weights | `sentence-transformers/all-MiniLM-L6-v2@1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | The official [model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) records Apache-2.0 and 384 dimensions. The exact safetensors SHA-256 is `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db`. |
| reranker weights | `cross-encoder/ms-marco-MiniLM-L6-v2@4bebbd56fc380a66525f95b03d4ec1a4b41a4f1e` | The official [model revision](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2/tree/4bebbd56fc380a66525f95b03d4ec1a4b41a4f1e) records Apache-2.0 and the CrossEncoder path. Safetensors SHA-256 is `821d1aa69520101d6e0737f78a042ae25b19e5cb9160701909d10434f4aeb0ae`. |

The lock resolves sentence-transformers dependencies for the optional group, but M6 does not treat
transitive PyTorch/Transformers versions as an M11 training/serving decision. Real weights are not
fetched implicitly. Production adapters require a pre-provisioned local directory with the exact
safetensors checksum and `trust_remote_code=False`; the default test/demo path uses named
deterministic fakes. This validates dependency resolution and contract wiring, not real-model
quality or representative latency.

## M7 hosted-LLM pins — verified and locked 2026-09-01

| Package/configuration | Exact pin | Official evidence / use |
|---|---:|---|
| OpenAI Python SDK | `openai==3.6.0` | The exact [PyPI release](https://pypi.org/project/openai/3.6.0/) supports Python 3.8+ and was resolved with CPython 3.13.15. The official [SDK documentation](https://developers.openai.com/api/docs/libraries) identifies the `openai` package and Responses API client. |
| OpenAI model snapshot | `gpt-5.4-mini-2026-03-17` | The official [GPT-5.4 mini model page](https://developers.openai.com/api/docs/models/gpt-5.4-mini) names this immutable snapshot and documents Responses plus structured-output support. |
| API pattern | Responses API with strict JSON Schema | The official [create response reference](https://developers.openai.com/api/reference/resources/responses/methods/create) documents `store`, strict JSON-schema text output, `max_output_tokens`, tools and usage metadata used by the adapter. |

The SDK lives in the optional `ai` group; LangChain/LangChain OpenAI were not added because the
small provider adapter does not need their abstraction/runtime surface. The adapter fixes the model
snapshot, disables provider-side response storage, exposes no tools, rejects invalid output and
uses explicitly reviewed external pricing/retention/training/region configuration. No API call was
made during M7 verification, so hosted quality, latency, billed cost, retention and regional
behavior remain not yet validated.

## M8 dependency decision — verified 2026-09-01

M8 adds no dependency. Python `dataclasses`, `json`, `hashlib`, `pathlib` and inert `ast.parse`
provide the strict contract/static adapter; existing Django/DRF/session/CSRF/database facilities
provide persistence and review. No formatter, type checker, test runner, patch utility, shell,
container runtime or provider is invoked on generated content in M8. Their appearance as proposed
commands is data only. This preserves the verified M7 lock unchanged and leaves runner/backend
selection to the RP-0801 threat review.

## M9 dependency/image decision — verified 2026-09-02

M9 adds no Python package. Plan/result hashing/signing, bounded process control and the Docker CLI
adapter use the standard library; the fixture image reuses `pytest==9.1.1`. ADR-018 requires the
verified Docker Engine 29.7.2 line on a dedicated rootless Linux host, but hosted CI may use its
ephemeral engine only for the explicit known-fixture probes.

The fixture Dockerfile pins the official multi-platform
`python:3.13.15-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e`
index resolved from Docker Hub on 2026-09-02. The built runner itself is selected by exact local
image ID and must carry labels matching runner version `releaseproof-fixture-runner-v1` and frozen
fixture-tree hash `d0bb7d8a86b163ecf690cee8d04616b47c756a9bfea2d43d79729c3966d82043`.
Mutable tags are not accepted in an execution plan.

## Dependency and image management

- Use only uv for the Python environment; commit `pyproject.toml`, `.python-version` and `uv.lock`.
- Set `.python-version` to `3.13.15` and configure uv's required version as `0.12.6`.
- Direct runtime/development requirements use exact pins; `uv.lock` records the complete transitive resolution.
- Separate later `ml`, `semantic`, `ai`, `e2e` and `observability` groups and create them only in the owning milestone.
- Release and Compose images use exact tags plus OCI manifest digests. Resolve digests on the actual target architecture during M1; do not invent them in documentation.
- Model artifacts use exact registry identifiers/checksums; prompts, FTS, features and schemas use semantic version plus content hash.
- Upgrade intentionally with unit/integration/security tests and relevant frozen ML/RAG/LLM evaluation; never float production dependencies.

## License and deployment notes

- SeaweedFS is Apache-2.0; MinIO OSS is excluded because it is archived/unmaintained, not merely because of license preference.
- Redis distribution/deployment licensing must be reviewed for the chosen deployment form before commercial distribution.
- Public repository data and model artifacts retain their own license/usage metadata; a permissive library license does not grant rights to model data or customer code.
- Optional model/provider packages are not product requirements until their milestone accepts their license, privacy, hardware and operational cost.
