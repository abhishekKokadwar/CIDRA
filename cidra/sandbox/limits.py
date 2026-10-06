"""Resource caps. See docs/6_sandbox_spec.md §4.

One place, referenced everywhere. Never remove a limit — raise it if a legitimate
fixture needs more, and record why here.
"""

# Built from sandbox/Dockerfile: python:3.11-slim + git + pytest/coverage + the non-root user.
# git is needed by `git apply`; baking the user in means no root exec at runtime.
IMAGE = "cidra-sandbox:base"

# The Python the default image runs, and the other versions a repo's CI may ask
# for. Each is the same Dockerfile on a digest-pinned base (SR-18), tagged
# cidra-sandbox:py<version> and built the first time a run needs it. Refresh with
#   docker buildx imagetools inspect python:<version>-slim --format '{{.Manifest.Digest}}'
DEFAULT_PYTHON = "3.11"
# 3.6 is absent: its last image is on a Debian release whose package index is gone.
PYTHON_IMAGES = {
    "3.7": "python:3.7-slim@sha256:b53f496ca43e5af6994f8e316cf03af31050bf7944e0e4a308ad86c001cf028b",
    "3.8": "python:3.8-slim@sha256:1d52838af602b4b5a831beb13a0e4d073280665ea7be7f69ce2382f29c5a613f",
    "3.9": "python:3.9-slim@sha256:2d97f6910b16bd338d3060f261f53f144965f755599aab1acda1e13cf1731b1b",
    "3.10": "python:3.10-slim@sha256:d8e262e069903a0b7790cd17a66d5343b2f04b9d9e19dc70f152c50fb511acfe",
    "3.12": "python:3.12-slim@sha256:ddb0207ae1f0356c2b724d740769b0c5f5f51cc54a0525178f721825f78fe74c",
    "3.13": "python:3.13-slim@sha256:2b6e177adb67a564bba97e6f0eab8760a7dc3645582d70277a055a4327a737e5",
}

# pytest/coverage for the Pythons the Dockerfile's default pins no longer support.
TEST_TOOLS = {
    "3.7": "pytest==7.4.4 coverage==7.2.7",
    "3.8": "pytest==8.3.5 coverage==7.6.1",
    "3.9": "pytest==8.4.2 coverage==7.10.7",
}


def image_for(python: str | None) -> str:
    """The sandbox image tag for a Python version; the default image for anything else."""
    return f"cidra-sandbox:py{python}" if python in PYTHON_IMAGES else IMAGE

# Resource caps
MEM_LIMIT = "2g"  # hard ceiling
MEMSWAP_LIMIT = "2g"  # == MEM_LIMIT => swap disabled
CPU_QUOTA = 100_000  # 1.0 CPU
CPU_PERIOD = 100_000
PIDS_LIMIT = 256  # fork-bomb ceiling

# Timeouts (seconds), per step
TIMEOUTS = {
    "checkout": 60,
    "install": 300,  # the slow one; network is on here
    "test": 300,
    "verify": 300,
}

# Container
USER = "cidra"  # non-root
UID = 1000
WORKDIR = "/work"
# pip --target dir, copied from the install container into the session container.
SITE = "/home/cidra/site"
AUTO_REMOVE = True

# Output capture — logs go to the LLM, so they are bounded.
TAIL_BYTES = 16_000
