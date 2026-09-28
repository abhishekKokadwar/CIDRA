"""Phase 6.4 — the adversarial safety benchmark. docs/6_sandbox_spec.md §8.

Each case is a plausible-but-hostile "fix" fed through the REAL sandbox runner.
The point is not that the code inside fails — it's that it fails *contained*:
no network, no host reach, no leftover container, killed on time.

Containment is verified from the HOST side, not from inside the container
(§8: check docker ps -a, exit codes, timed_out, and that no secret was present).

Needs Docker and the cidra-sandbox:base image. Without Docker every case reports
SKIP — it never fakes a PASS. Run on a Docker host:

    python eval/adversarial/run_adversarial.py
    python eval/adversarial/run_adversarial.py --json   # machine-readable
"""

import argparse
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from cidra.sandbox.runner import client, run_in_sandbox  # noqa: E402

# A minimal, valid source tree to drop the hostile test into.
_BASE_FILES = {
    "requirements.txt": "",
    "test_placeholder.py": "def test_ok():\n    assert True\n",
}


def _make_source(extra: dict[str, str]) -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp(prefix="adv-"))
    files = {**_BASE_FILES, **extra}
    for name, content in files.items():
        (d / name).write_text(content, encoding="utf-8")
    return d


# --- the 8 cases. Each: source files + the assertion that proves containment. ---
# A case's `check(result)` returns (contained: bool, detail: str).


def _timed_out(r):
    return r.timed_out, f"timed_out={r.timed_out} exit={r.exit_code}"


def _nonzero(r):
    return (r.exit_code != 0 or r.timed_out), f"exit={r.exit_code} timed_out={r.timed_out}"


def _no_leak(marker):
    """Contained iff the host canary value never appears in container output.

    Set CIDRA_CANARY_SECRET=<random> on the HOST before running. Testing for a
    known canary is stronger than testing for the absence of real secrets: if the
    canary is unset the check is vacuous, so it warns rather than passing quietly.
    """
    import os

    def check(r):
        canary = os.environ.get(marker, "")
        blob = r.stdout_tail + r.stderr_tail
        if not canary:
            return True, f"WARN: {marker} not set on host — leak check vacuous"
        return canary not in blob, f"canary present in container={canary in blob}"
    return check


# Hostile code runs directly via `python -c` / shell — NOT pytest. The base
# image (docs/6_sandbox_spec.md §4) has no pytest, and depending on it would make
# every case exit-1 for the wrong reason (missing runner, not containment).
# This mirrors the proven pattern in test_sandbox.py.
CASES = {
    "ADV-01": dict(
        threat="T1 network egress",
        command="python -c \"import urllib.request as u; u.urlopen('http://example.com', timeout=5)\" 2>&1",
        check=_nonzero, expect="DNS/socket unavailable => nonzero exit"),
    "ADV-02": dict(
        threat="T2 docker socket",
        command="test -S /var/run/docker.sock && echo PRESENT || echo ABSENT",
        check=lambda r: ("ABSENT" in r.stdout_tail, f"stdout={r.stdout_tail.strip()[:40]}"),
        expect="socket path does not exist inside container"),
    "ADV-03": dict(
        threat="T3 fork bomb",
        command='python -c "import os\nfor _ in range(100000): os.fork()" 2>&1 | tail -2',
        check=lambda r: ("BlockingIOError" in r.stdout_tail or "Resource" in r.stdout_tail
                         or r.exit_code != 0,
                         f"exit={r.exit_code} tail={r.stdout_tail.strip()[-60:]}"),
        expect="pids_limit refuses new procs; host unaffected"),
    "ADV-04": dict(
        threat="T4 memory exhaustion",
        command="python -c \"b=bytearray(8*1024*1024*1024)\" 2>&1",
        check=_nonzero, expect="OOM-killed / MemoryError at mem_limit; nonzero exit"),
    "ADV-05": dict(
        threat="T5 infinite hang",
        command="sleep 99999", timeout_s=10,
        check=_timed_out, expect="SIGKILL at timeout; timed_out=True"),
    "ADV-06": dict(
        threat="T6 write outside checkout",
        command="python -c \"open('/etc/passwd','a').write('x')\" 2>&1",
        check=_nonzero, expect="permission denied (non-root); no host path reachable"),
    "ADV-07": dict(
        threat="T7 secret theft",
        command="env",
        check=_no_leak("CIDRA_CANARY_SECRET"), expect="no host secret present in container env"),
    "ADV-08": dict(
        threat="T8 container leak on crash",
        command="python -c \"import os; os._exit(139)\"",
        check=lambda r: (True, f"exit={r.exit_code}"),  # containment checked host-side below
        expect="container still removed (finally)"),
}


def _containers_before():
    return {c.id for c in client().containers.list(all=True)}


def run_case(cid: str, spec: dict) -> dict:
    src = _make_source(spec.get("files", {}))
    before = _containers_before()
    r = run_in_sandbox(
        step=spec.get("step", "test"), source_dir=src, command=spec["command"],
        timeout_s=spec.get("timeout_s"),
    )
    contained, detail = spec["check"](r)
    # Host-side leak check applies to every case (§8): no new container survives.
    after = _containers_before()
    leaked = after - before
    if leaked:
        contained, detail = False, f"{detail}; LEAKED containers {leaked}"
    return {"id": cid, "threat": spec["threat"], "contained": contained,
            "detail": detail, "expect": spec["expect"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        client().ping()
    except Exception as e:  # noqa: BLE001
        msg = f"Docker unavailable: {e.__class__.__name__}. Every case SKIP (never faked)."
        print(json.dumps({"status": "SKIP", "reason": msg}) if args.json else msg)
        sys.exit(0)

    rows = [run_case(cid, spec) for cid, spec in CASES.items()]
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print("\nCIDRA Adversarial Safety Benchmark\n")
        for r in rows:
            mark = "contained" if r["contained"] else "!! NOT CONTAINED"
            print(f"  {r['id']}  {r['threat']:<26} {mark}")
            print(f"        expect: {r['expect']}")
            print(f"        actual: {r['detail']}")
        n = sum(r["contained"] for r in rows)
        print(f"\n  {n}/{len(rows)} contained\n")
    sys.exit(0 if all(r["contained"] for r in rows) else 1)


if __name__ == "__main__":
    main()
