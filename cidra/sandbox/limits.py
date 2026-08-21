"""Resource caps. See docs/6_sandbox_spec.md §4.

One place, referenced everywhere. Never remove a limit — raise it if a legitimate
fixture needs more, and record why here.
"""

# Built from sandbox/Dockerfile: python:3.11-slim + git + the non-root user.
# git is needed by `git apply`; baking the user in means no root exec at runtime.
IMAGE = "cidra-sandbox:base"

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
