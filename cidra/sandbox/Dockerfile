# Sandbox base. See docs/6_sandbox_spec.md §4.
# Built once, reused for every run — keeps `git apply` available without
# giving the container network access at patch time.
# Pinned by digest (SR-18): the tag can move, the digest cannot. Refresh with
#   docker pull python:3.11-slim && docker inspect --format '{{index .RepoDigests 0}}' python:3.11-slim
# Other Python versions are built from this same file by sandbox/runner.py,
# which passes the digest-pinned image for that version (sandbox/limits.py).
ARG PYTHON_IMAGE=python:3.11-slim@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b
FROM ${PYTHON_IMAGE}

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

# The test runner must exist even when the repo's requirements don't list it:
# a missing pytest exits 127, which is not a reproduced failure. coverage is for
# SBFL. Installed system-wide (as root) so /usr/local/bin is on the runner's
# PATH; a repo-pinned version installed by the install step still wins.
ARG TEST_TOOLS="pytest==9.1.1 coverage==7.16.2"
RUN pip install --no-cache-dir ${TEST_TOOLS}

# Non-root user baked in, so no root exec is needed at runtime.
RUN useradd -u 1000 -m cidra && mkdir -p /work && chown cidra /work

USER cidra
WORKDIR /work
