#!/usr/bin/env bash
# What a user gets from `pip install cidra`, run from outside the checkout so
# nothing can be imported from the source tree (CI's package job).
#
#   scripts/smoke_installed.sh <python of a venv with the wheel installed> <cidra-practice: URL or clone with its branches>
#
# 1. the `cidra` command starts
# 2. the sandbox image builds from the installed package (the README's step)
# 3. `cidra dashboard` serves its page, every file the page loads, and no runs
# 4. `cidra action` repairs a failing practice commit end to end: the log comes
#    from a stand-in GitHub API (scripts/fake_github.py), the model's answers
#    from a stand-in model (scripts/fake_llm.py), and the report must arrive on
#    the failing commit as a verified fix.
set -euo pipefail
PY=$1
PRACTICE=$2
REPO=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)
PIDS=()
trap 'kill "${PIDS[@]}" 2>/dev/null; wait 2>/dev/null; rm -rf "$WORK" 2>/dev/null || true' EXIT
cd "$WORK"
export CIDRA_ENV_FILE="$WORK/.env"  # no developer .env leaks in

wait_for() { for _ in $(seq 1 60); do curl -fsS -o /dev/null "$1" 2>/dev/null && return 0; sleep 1; done; echo "never came up: $1"; return 1; }
# A server left over from an earlier run would answer for the version under test.
port_free() { ! curl -s -o /dev/null "http://127.0.0.1:$1/" || { echo "port $1 is already in use"; exit 1; }; }

echo "== 1. the cidra command"
"$(dirname "$PY")/cidra" --help >/dev/null

echo "== 2. the sandbox image from the installed package"
bash "$REPO/scripts/retry.sh" docker build -q -t cidra-sandbox:base "$("$PY" -c 'import cidra, os; print(os.path.join(os.path.dirname(cidra.__file__), "sandbox"))')"

echo "== 3. the installed dashboard"
port_free 8799
mkdir dash && cd dash
"$PY" -m cidra.cli dashboard --no-open --port 8799 >"$WORK/dashboard.log" 2>&1 &
PIDS+=($!)
cd "$WORK"
wait_for http://127.0.0.1:8799/
page=$(curl -fsS -H 'accept: text/html' http://127.0.0.1:8799/)
for asset in $(grep -o '/assets/[^"]*' <<<"$page") /favicon.svg /cidra_logo.png; do
  curl -fsS -o /dev/null "http://127.0.0.1:8799$asset" || { echo "not served: $asset"; exit 1; }
done
[ "$(curl -fsS http://127.0.0.1:8799/telemetry.json | "$PY" -c 'import json,sys; print(len(json.load(sys.stdin)["runs"]))')" = 0 ]

echo "== 4. cidra action on a failing commit"
bash "$REPO/scripts/retry.sh" git clone -q --branch fix-02-assertion "$PRACTICE" target
SHA=$(git -C target rev-parse HEAD)
port_free 8798; port_free 8797
"$PY" "$REPO/scripts/fake_llm.py" "$REPO/eval/fixtures/F-02/fake_llm.json" --port 8798 &
PIDS+=($!)
"$PY" "$REPO/scripts/fake_github.py" "$REPO/eval/fixtures/F-02/raw.log" --out comments.json --port 8797 &
PIDS+=($!)
wait_for http://127.0.0.1:8797/repos/o/r/pulls
cat >event.json <<EOF
{"workflow_run": {"id": 1, "head_sha": "$SHA", "head_branch": "fix-02-assertion",
                  "path": ".github/workflows/ci.yml", "conclusion": "failure", "pull_requests": []}}
EOF
GITHUB_EVENT_PATH="$WORK/event.json" GITHUB_REPOSITORY=helpmecode69/cidra-practice GITHUB_RUN_ID=1 \
GITHUB_SHA="$SHA" GITHUB_WORKSPACE="$WORK/target" \
CIDRA_GITHUB_API=http://127.0.0.1:8797 CIDRA_GITHUB_TOKEN=fake CIDRA_API_KEY=fake \
CIDRA_BASE_URL=http://127.0.0.1:8798/v1 CIDRA_MODEL_ANALYZE=fake-model CIDRA_MODEL_FIX=fake-model GEMINI_API_KEY= \
  "$PY" -m cidra.cli action
"$PY" - "$SHA" <<'EOF'
import json, sys
posted = json.load(open("comments.json"))
on_commit = [c for c in posted if c["path"] == f"/repos/helpmecode69/cidra-practice/commits/{sys.argv[1]}/comments"]
assert len(on_commit) == 1, posted
assert "verified fix" in on_commit[0]["body"], on_commit[0]["body"][:500]
print("report posted on the failing commit: verified fix")
EOF
echo "ok: the installed package works"
