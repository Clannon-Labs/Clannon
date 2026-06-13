# Vraksha sandbox image — the locked-down environment expert code runs in (via the
# Docker-backed Workspace). The sandbox has NO network at runtime, so anything an
# expert might need to import must be baked in here. Build it and point the workspace
# at it with VRAKSHA_SANDBOX_IMAGE:
#
#   docker build -f docker/sandbox.Dockerfile -t vraksha-sandbox:latest .
#   export VRAKSHA_SANDBOX_IMAGE=vraksha-sandbox:latest
#
# Kept small: a slim Python plus the data + test stack the code and data-analysis
# experts rely on. Non-root is enforced at `docker run` time (--user), not here.
FROM python:3.12-slim

RUN pip install --no-cache-dir \
        pandas \
        numpy \
        matplotlib \
        pytest \
    && rm -rf /root/.cache/pip

# default matplotlib to a headless backend (no display inside the sandbox)
ENV MPLBACKEND=Agg

WORKDIR /workspace
