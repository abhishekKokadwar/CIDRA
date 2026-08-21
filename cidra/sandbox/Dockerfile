# Sandbox base. See docs/6_sandbox_spec.md §4.
# Built once, reused for every run — keeps `git apply` available without
# giving the container network access at patch time.
FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

# Non-root user baked in, so no root exec is needed at runtime.
RUN useradd -u 1000 -m cidra && mkdir -p /work && chown cidra /work

USER cidra
WORKDIR /work
