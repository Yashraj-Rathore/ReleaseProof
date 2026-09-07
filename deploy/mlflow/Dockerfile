FROM python:3.13.15-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e

LABEL org.releaseproof.component="mlflow-tracking"
LABEL org.releaseproof.mlflow-version="3.15.2"

RUN python -m pip install --no-cache-dir --disable-pip-version-check \
    "boto3==1.43.81" \
    "mlflow==3.15.2" \
    "psycopg[binary]==3.3.4"

ENV HOME=/tmp \
    MLFLOW_HOME=/tmp/mlflow \
    PYTHONUNBUFFERED=1

USER 65532:65532
EXPOSE 5000
