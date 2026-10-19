#!/usr/bin/env bash
# Run a download step (git clone, docker build, npm ci, a browser install) up to
# 3 times, so a GitHub, registry or PyPI hiccup does not fail CI as if the code
# were broken. Each retry leaves a warning on the run. Never wrap a test in this:
# a test that passes on its second try is a flaky test, and must fail.
#
#   bash scripts/retry.sh git clone --quiet https://github.com/... dir
#
# RETRY_DELAY (seconds, default 15) is multiplied by the attempt number.
set -uo pipefail
for attempt in 1 2 3; do
  "$@" && exit 0
  status=$?
  [ "$attempt" = 3 ] && break
  echo "::warning::attempt $attempt failed (exit $status), retrying: $*"
  sleep $((${RETRY_DELAY:-15} * attempt))
done
echo "::error::failed 3 times: $*"
exit "$status"
