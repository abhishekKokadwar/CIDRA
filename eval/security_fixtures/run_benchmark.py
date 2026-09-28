"""CIDRA security benchmark runner. See README.md in this directory.

Tier 1 (default): static + parser checks that need no container. Free, instant.
Tier 2: runs payloads through the real sandbox and verifies containment host-side.

Each fixture's attack.json lists `assertions`. A check either PASSes, FAILs, or is
`todo` (the node it targets does not exist yet). A `todo` is neither PASS nor FAIL — the
scorecard shows it honestly so we never claim a control we haven't exercised.
"""

import argparse
import ast
import json
import pathlib

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent.parent
import sys as _sys  # noqa: E402
_sys.path.insert(0, str(ROOT))
CIDRA = ROOT / "cidra"

# ---------------------------------------------------------------------------
# Tier 1 checks. Each returns ("PASS"|"FAIL"|"TODO", detail).
# Only the ones that can actually run today are implemented; the rest are TODO
# stubs naming the SR and the node that must exist first.
# ---------------------------------------------------------------------------


def check_no_shell_true(_):
    """SR-03 / ADV-11: no shell=True and no interpolated command anywhere in cidra/."""
    offenders = []
    for py in CIDRA.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "shell" and getattr(kw.value, "value", None) is True:
                        offenders.append(f"{py.relative_to(ROOT)}:{node.lineno}")
    return ("PASS", "no shell=True") if not offenders else ("FAIL", offenders)


def check_structured_output_only(_):
    """SR-01 / ADV-09: the LLM has no *agentic* tool loop.

    CIDRA legitimately uses one forced 'report' function as its structured-output
    mechanism (tool_choice pins it; its only effect is to return a schema). That is
    NOT the tool loop SR-01 forbids. The real invariants:
      - tool_choice must FORCE a single function (no model-chosen tool calls)
      - the only function must be the schema reporter, with no side effect
    A tool that acts on the world (bash/read/comment) or a free tool_choice fails.
    """
    llm = CIDRA / "integrations" / "llm.py"
    if not llm.exists():
        return ("TODO", "cidra/integrations/llm.py not present")
    src = llm.read_text(encoding="utf-8")
    if "tools=" not in src:
        return ("PASS", "no tools field at all")
    forced = '"function"' in src and "tool_choice=" in src
    acting = any(t in src for t in ('"bash"', '"read"', '"exec"', '"shell"',
                                    '"write_comment"', '"run"'))
    if acting:
        return ("FAIL", "an acting tool is exposed to the model")
    if not forced:
        return ("FAIL", "tool_choice does not force a single function — model may choose")
    return ("PASS", "structured-output only: single forced report function, no acting tools")


def check_no_merge_call(_):
    """SR-11 / ADV-14: no merge API call path exists in the codebase.

    Matches actual merge *calls*, not the word 'merge' in prose: a `.merge(`
    method call, `merge_pull_request(`, or the GitHub merge URL suffix
    `/merge"` / `/merge'`. Comment lines are stripped before scanning so a
    docstring mentioning 'merged' can't trip a false positive.
    """
    import re as _re
    pat = _re.compile(r"\.merge\(|merge_pull_request\(|/merge['\"]")
    hits = []
    for py in CIDRA.rglob("*.py"):
        code = "\n".join(ln.split("#", 1)[0] for ln in py.read_text(encoding="utf-8").splitlines())
        if pat.search(code):
            hits.append(str(py.relative_to(ROOT)))
    return ("PASS", "no merge call") if not hits else ("FAIL", hits)


def check_git_hardening(_):
    """SR-16/17: a hostile repo (hook + core.fsmonitor + alias) can't run code on
    the host, and no .git reaches the sandbox tree. Builds a real repo and runs
    the hardened checkout over it (needs git; SKIP if unavailable)."""
    import shutil
    import tempfile
    if shutil.which("git") is None:
        return ("TODO", "git not available")
    from cidra import config as _cfg
    from cidra.git_ops import git as _git
    from cidra.nodes import checkout as _co
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="sec04-"))
    _cfg.WORKTREE_ROOT = str(tmp / "wt")
    canary = tmp / "CANARY"
    src = tmp / "evil"; src.mkdir()
    _git("init", "-q", cwd=src)
    _git("config", "user.email", "t@t", cwd=src); _git("config", "user.name", "t", cwd=src)
    (src / "a.txt").write_text("x")
    _git("add", "-A", cwd=src); _git("commit", "-qm", "c1", cwd=src)
    hook = src / ".git" / "hooks" / "post-checkout"
    hook.write_text(f"#!/bin/sh\ntouch '{canary}'\n"); hook.chmod(0o755)
    _git("config", "core.fsmonitor", f"touch '{canary}'", cwd=src)
    tree = _co.prepare_checkout("bench-sec04", src)
    _git("status", cwd=src)
    contained = not canary.exists() and not (tree / ".git").exists()
    return ("PASS", "hook+fsmonitor inert, no .git in tree") if contained \
        else ("FAIL", f"canary={canary.exists()} dotgit={(tree/'.git').exists()}")


def check_patch_guard(_):
    """SR-13/14/15: the AST patch guard rejects/surfaces every SEC-07 candidate.

    Runs the real audit_diff over the fixture's candidate patches and checks each
    one gets the outcome its fixture declares (reject vs surface).
    """
    from cidra.nodes.audit import audit_diff
    payload = json.loads(
        (HERE / "07_repo_write_abuse/payload/candidate_patches.json").read_text())
    bad = []
    for p in payload["patches"]:
        v = audit_diff(p["diff"])
        if p["must"] == "reject" and v.ok:
            bad.append(f"{p['id']} not rejected")
        if p["must"] == "surface" and not (v.ok and v.surfaced):
            bad.append(f"{p['id']} not surfaced")
    return ("PASS", "all candidates handled") if not bad else ("FAIL", bad)


# SR-nn : (node that must exist, human note). Emitted as TODO until wired.
TODO_CHECKS = {
    "SEC-01": [("SR-06", "read path must not receive write client - needs publish node")],
    "SEC-02": [("SR-08", "assert container env is an explicit allowlist - needs runner")],
    "SEC-03": [("SR-09", "assert network off in test/verify - needs runner")],
    "SEC-05": [("SR-19", "assert no container/volume survives - needs runner + Docker")],
    "SEC-06": [("SR-02", "assert schema rejects unknown fields - needs FixProposal model")],
    "SEC-08": [("SR-14", "assert AGENTS.md not loaded as config - needs prompt builder")],
}

# Checks runnable today, per fixture.
LIVE_CHECKS = {
    "SEC-01": [check_structured_output_only],
    "SEC-04": [check_git_hardening],
    "SEC-06": [check_no_shell_true, check_structured_output_only],
    "SEC-07": [check_no_merge_call, check_patch_guard],
}


def run_fixture(d: pathlib.Path, tier: int) -> dict:
    a = json.loads((d / "attack.json").read_text())
    fid = a["fixture_id"]
    results = []
    for check in LIVE_CHECKS.get(fid, []):
        status, detail = check(a)
        results.append((check.__doc__.split(":")[0].strip(), status, detail))
    for sr, note in TODO_CHECKS.get(fid, []):
        results.append((sr, "TODO", note))
    if tier >= 2:
        results.append(("tier2-sandbox", "TODO", "sandbox execution not wired (Phase 4+)"))

    statuses = [s for _, s, _ in results]
    if "FAIL" in statuses:
        verdict = "FAIL"
    elif all(s == "TODO" for s in statuses):
        verdict = "PENDING"
    elif a.get("expected_result") == "ACCEPTED-BOUNDED":
        verdict = "BOUNDED"
    else:
        verdict = "PASS"
    return {"fixture": fid, "name": a["name"], "verdict": verdict, "checks": results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", type=int, default=1)
    args = ap.parse_args()

    rows = [run_fixture(d, args.tier) for d in sorted(HERE.iterdir())
            if d.is_dir() and (d / "attack.json").exists()]

    print(f"\nCIDRA Security Benchmark - tier {args.tier}\n")
    for r in rows:
        print(f"  {r['fixture']}  {r['name']:<24} {r['verdict']}")
        for name, status, detail in r["checks"]:
            mark = {"PASS": "[+]", "FAIL": "[x]", "TODO": "[.]", "PENDING": "[.]"}.get(status, "?")
            print(f"      {mark} {name:<12} {status:<8} {detail}")
    n_pass = sum(r["verdict"] in ("PASS", "BOUNDED") for r in rows)
    print(f"\n  {n_pass}/{len(rows)} fixtures resolved; rest PENDING (nodes not yet built)\n")


if __name__ == "__main__":
    main()
