FROM python:3.13.15-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e

LABEL org.releaseproof.fixture-tree-sha256="70b1ebeb3d2257fa88667f06d8df3690de118dd277ec993f805d1851c17b4673"
LABEL org.releaseproof.runner-version="releaseproof-fixture-runner-v1"

RUN python -m pip install --no-cache-dir --disable-pip-version-check pytest==9.1.1
COPY tests/fixtures/repositories/releaseproof_fixture /opt/fixture/repository
COPY runner/fixture_image/entrypoint.py /opt/releaseproof/entrypoint.py

WORKDIR /workspace
USER 65532:65532
ENTRYPOINT ["python", "/opt/releaseproof/entrypoint.py"]
