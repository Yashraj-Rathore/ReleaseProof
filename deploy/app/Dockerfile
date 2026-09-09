# syntax=docker/dockerfile:1.7

FROM python:3.13.15-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/releaseproof/.venv

WORKDIR /build
RUN python -m pip install --no-cache-dir "uv==0.12.6"
COPY pyproject.toml uv.lock README.md .python-version ./
RUN uv sync --frozen --no-dev --no-install-project \
    --group ml \
    --group ai \
    --group agent \
    --group governance \
    --group observability

COPY adapters ./adapters
COPY apps ./apps
COPY artifacts/evaluation/m13_governance_eval_v1.json ./artifacts/evaluation/m13_governance_eval_v1.json
COPY manage.py ./manage.py
COPY models/public ./models/public
COPY packages ./packages
COPY workers ./workers
RUN DJANGO_SETTINGS_MODULE=apps.web.releaseproof.settings.test \
    /opt/releaseproof/.venv/bin/python manage.py collectstatic --noinput

FROM python:3.13.15-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e AS runtime

ENV PATH=/opt/releaseproof/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY --from=builder /opt/releaseproof/.venv /opt/releaseproof/.venv
COPY --from=builder --chown=65532:65532 /build/adapters ./adapters
COPY --from=builder --chown=65532:65532 /build/apps ./apps
COPY --from=builder --chown=65532:65532 /build/artifacts ./artifacts
COPY --from=builder --chown=65532:65532 /build/manage.py ./manage.py
COPY --from=builder --chown=65532:65532 /build/models ./models
COPY --from=builder --chown=65532:65532 /build/packages ./packages
COPY --from=builder --chown=65532:65532 /build/staticfiles ./staticfiles
COPY --from=builder --chown=65532:65532 /build/workers ./workers

USER 65532:65532

ENTRYPOINT []
CMD ["gunicorn", "apps.web.releaseproof.wsgi:application", "--bind=0.0.0.0:8000", "--workers=2", "--threads=4", "--timeout=30", "--graceful-timeout=30", "--max-requests=1000", "--max-requests-jitter=100"]
