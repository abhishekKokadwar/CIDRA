"""Build the `bugsinpy` group of the real-failure corpus.

Walks BugsInPy in a fixed order, tries each candidate in the sandbox and keeps
the ones that pass every rule in eval/corpus/README.md. No model is called.
Safe to re-run: candidates already kept or dropped are skipped.

    python eval/build_bugsinpy.py                 # all projects
    python eval/build_bugsinpy.py thefuck httpie  # some projects
"""

import json
import pathlib
import re
import shlex
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cidra import config  # noqa: E402
from cidra.nodes.checkout import prepare_checkout, remove_checkout  # noqa: E402
from cidra.sandbox import limits  # noqa: E402
from cidra.sandbox.runner import Session  # noqa: E402
from eval import corpus_repo  # noqa: E402

CORPUS = ROOT / "eval" / "corpus"
EXCLUDED = CORPUS / "EXCLUDED.json"
BUGSINPY_URL = "https://github.com/soarsmu/BugsInPy.git"
NEEDS_BUILD = {"pandas", "matplotlib", "spacy"}  # C or Cython extensions
KEEP_PER_PROJECT, TRIALS_PER_PROJECT, INSTALL_FAILURES_TO_ABANDON = 5, 12, 3
MAX_FILES, MAX_LINES = 3, 30

_PIN = re.compile(r"^[A-Za-z0-9_.\-\[\]]+==[\w.!+*-]+$")
_E_LINE = re.compile(r"^E\s+(\S.*)$")
_FAILED = re.compile(r"^FAILED (\S+)", re.MULTILINE)


def _info(path: pathlib.Path) -> dict:
    return dict(re.findall(r'^(\w+)\s*=\s*"?([^"\r\n]*)"?\s*$', path.read_text(encoding="utf-8"), re.MULTILINE))


def _is_test(path: str) -> bool:
    parts = path.lower().split("/")
    return any(p in ("test", "tests", "testing") for p in parts[:-1]) or \
        parts[-1].startswith("test_") or parts[-1].endswith("_test.py") or parts[-1] == "conftest.py"


def expected_category(log: str) -> tuple[str, str]:
    """(category, first error line). assertion_error only when every failure
    opens with a failed assert; anything else is outside CIDRA's stated scope."""
    firsts, previous_was_e = [], False
    for line in log.splitlines():
        m = _E_LINE.match(line)
        if m and not previous_was_e:
            firsts.append(m.group(1))
        previous_was_e = line.startswith("E ")  # a blank "E   " line continues the block
    if firsts and all(re.match(r"(assert\b|AssertionError)", f) for f in firsts):
        return "assertion_error", firsts[0]
    return "unknown", firsts[0] if firsts else ""


def _exclude(record: dict, key: str, reason: str) -> None:
    record[key] = reason
    EXCLUDED.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"  drop {key}: {reason}", flush=True)


def trial(key: str, repo: str, failing: str, python: str, installs: list[str], test: str, diff: str):
    """(failing-run log, install command used) when the case passes rules 4-6,
    else (None, reason). `installs` are tried in order."""
    run_id = f"build-{key}"
    try:
        tree = prepare_checkout(run_id, repo, failing)
        with Session(tree, python) as session:
            install = next((c for c in installs if session.install(c).passed), None)
            if install is None:
                return None, "install: dependencies do not install in the sandbox, pinned or unpinned"
            red = session.run("test", test)
            if red.stdout_tail.startswith("...[truncated]"):
                # Warnings pushed the failure out of the captured output: run without them.
                test = test.replace("pytest -q ", "pytest -q -p no:warnings ", 1)
                red = session.run("test", test)
            if red.exit_code != 1:
                why = next((ln[1:].strip() for ln in red.stdout_tail.splitlines() if ln.startswith("E ")), "")
                return None, (f"failing state: pytest exit code {red.exit_code}, not ordinary test failures"
                              + (f" ({why[:100]})" if why else ""))
            if not session.apply_patch(diff).passed:
                return None, "fix: the non-test changes do not apply to the failing state"
            green = session.run("verify", test)
            if not green.passed:
                last = (green.stdout_tail.strip().splitlines() or [""])[-1].strip("= ")
                return None, f"fix: tests still fail with the fix applied (exit code {green.exit_code}: {last[:80]})"
            return red.stdout_tail, (install, test)
    except Exception as e:  # noqa: BLE001
        return None, f"sandbox error: {type(e).__name__}: {str(e)[:120]}"
    finally:
        remove_checkout(run_id)


def build_project(bip: pathlib.Path, project: str, excluded: dict) -> None:
    kept = len(list(CORPUS.glob(f"bip-{project.lower()}-*/meta.json")))
    tried = sum(1 for k, v in excluded.items() if k.startswith(f"{project}/") and
                v.startswith(("install:", "failing state:", "fix:", "sandbox error:"))) + kept
    install_failures = 0
    if project.lower() in NEEDS_BUILD:
        print(f"{project}: skipped, needs a compiled build", flush=True)
        return
    url = _info(bip / "projects" / project / "project.info")["github_url"].rstrip("/")
    bugs = sorted((int(p.name) for p in (bip / "projects" / project / "bugs").iterdir() if p.name.isdigit()))
    repo = None
    print(f"{project}: {len(bugs)} bugs", flush=True)
    for n in bugs:
        key, fid = f"{project}/{n}", f"bip-{project.lower()}-{n}"
        if kept >= KEEP_PER_PROJECT or tried >= TRIALS_PER_PROJECT:
            break
        if install_failures >= INSTALL_FAILURES_TO_ABANDON:
            print(f"  abandoned after {install_failures} install failures in a row", flush=True)
            break
        if key in excluded or (CORPUS / fid / "meta.json").exists():
            continue
        folder = bip / "projects" / project / "bugs" / str(n)
        info = _info(folder / "bug.info")
        python = ".".join(info["python_version"].split(".")[:2])
        if python != limits.DEFAULT_PYTHON and python not in limits.PYTHON_IMAGES:
            _exclude(excluded, key, f"python {python} has no sandbox image")
            continue
        try:
            repo = repo or corpus_repo.corpus_clone(url)
            if not all(info.get(k) for k in ("buggy_commit_id", "fixed_commit_id", "test_file")):
                raise ValueError("bug.info is missing a commit or the test file")
            buggy = corpus_repo.resolve(repo, info["buggy_commit_id"])
            fixed = corpus_repo.resolve(repo, info["fixed_commit_id"])
            tests = [t.strip() for t in info["test_file"].split(";") if t.strip()]
            changed = corpus_repo.git(repo, "diff", "--name-only", buggy, fixed).splitlines()
            source = [p for p in changed if not _is_test(p)]
            # Everything the fix touched on the test side comes along: a test often
            # needs a data file added in the same commit. Deleted files are left alone.
            present = set(corpus_repo.git(repo, "diff", "--name-only", "--diff-filter=d", buggy, fixed).splitlines())
            test_side = sorted({*tests, *(p for p in changed if _is_test(p) and p in present)})
            stat = corpus_repo.git(repo, "diff", "--numstat", buggy, fixed, "--", *source) if source else ""
            lines = sum(int(a) + int(b) for a, b, _ in (r.split("\t") for r in stat.splitlines()) if a.isdigit())
            if not source or len(source) > MAX_FILES or lines > MAX_LINES:
                _exclude(excluded, key, f"fix size: {len(source)} non-test files, {lines} lines")
                continue
            failing = corpus_repo.pin(repo, corpus_repo.with_files_from(repo, buggy, fixed, test_side))
            # Unstripped: a trailing blank context line is part of the patch.
            diff = subprocess.check_output(["git", "-C", repo, "diff", buggy, fixed, "--", *source],
                                           text=True, encoding="utf-8", errors="replace")
        except (subprocess.CalledProcessError, ValueError) as e:
            _exclude(excluded, key, f"repository: {str(e)[:120]}")
            continue

        raw = (folder / "requirements.txt").read_bytes()  # a few of these files are UTF-16
        text = raw.decode("utf-16" if raw[:2] in (bytes([255, 254]), bytes([254, 255])) else "utf-8", errors="replace")
        pins = [ln.strip() for ln in text.splitlines()]
        # Backports of standard-library modules are left out: the sandbox puts
        # installed packages ahead of the standard library, so they would shadow it.
        pins = [p for p in pins if _PIN.match(p) and
                p.lower().split("==")[0] not in {project.lower(), "dataclasses", "typing", "enum34", "asyncio"}]
        # A bug with no pinned dependencies still needs a valid pip command.
        pinned = "pip install --quiet " + (" ".join(shlex.quote(p) for p in pins) or "pytest")
        # Rule 4 fallback: the same packages at whatever version suits this Python.
        unpinned = "pip install --quiet " + (" ".join(shlex.quote(p.split("==")[0]) for p in pins) or "pytest")
        installs = list(dict.fromkeys([pinned, unpinned]))
        test = "python -m pytest -q " + " ".join(shlex.quote(t) for t in tests) + " 2>&1"

        print(f"  try  {key} (python {python}, {len(source)} files, {lines} lines)", flush=True)
        tried += 1
        log, reason = trial(fid, repo, failing, python, installs, test, diff)
        (install, test), reason = (reason, None) if log is not None else ((None, test), reason)
        if reason:
            install_failures = install_failures + 1 if reason.startswith("install:") else 0
            _exclude(excluded, key, reason)
            continue
        install_failures = 0

        category, first_error = expected_category(log)
        failed = _FAILED.findall(log)
        out = CORPUS / fid
        out.mkdir(parents=True, exist_ok=True)
        (out / "raw.log").write_text(log, encoding="utf-8", newline="\n")
        (out / "meta.json").write_text(json.dumps({
            "group": "bugsinpy", "source": f"BugsInPy {key}", "class": category, "known_fix": True,
            "repo_url": url, "failing_ref": buggy, "fix_ref": fixed,
            "failing_tests_from_fix": test_side, "held_out_paths": test_side,
            "install_command": install, "test_command": test, "python_version": python,
            "dependencies": "pinned" if install == pinned else "unpinned",
            "log_origin": "pytest output of the failing state in the sandbox, not a CI log",
            "fix_size": {"files": len(source), "lines": lines},
        }, indent=2) + "\n", encoding="utf-8")
        (out / "expected.json").write_text(json.dumps({
            "expected_outcome": "verified_fix" if category == "assertion_error" else "diagnosis_only",
            "expected_analysis": {"category": category},
            "note": "Set mechanically from the log; see eval/corpus/README.md.",
        }, indent=2) + "\n", encoding="utf-8")
        (out / "fake_llm.json").write_text(json.dumps({
            "Analysis": {"category": category, "confidence": 0.9, "evidence": first_error[:300],
                         "proposed_action": "Apply the project's own fix.",
                         "failing_test": failed[0] if failed else tests[0]},
            "Patch": {"diff": diff, "target_file": source[0],
                      "rationale": "Reference patch: the project's own fix, non-test files only."},
        }, indent=2) + "\n", encoding="utf-8")
        kept += 1
        print(f"  keep {fid}: {category} ({first_error[:70]})", flush=True)


def main() -> int:
    CORPUS.mkdir(parents=True, exist_ok=True)
    bip = pathlib.Path(config.WORKTREE_ROOT).resolve() / "corpus" / "_bugsinpy"
    if not (bip / ".git").exists():
        bip.parent.mkdir(parents=True, exist_ok=True)
        subprocess.check_call(["git", "clone", "--quiet", "--depth", "1", BUGSINPY_URL, str(bip)])
    excluded = json.loads(EXCLUDED.read_text(encoding="utf-8")) if EXCLUDED.exists() else {}
    projects = sorted((p.name for p in (bip / "projects").iterdir() if p.is_dir()), key=str.lower)
    for project in [p for p in projects if not sys.argv[1:] or p in sys.argv[1:]]:
        build_project(bip, project, excluded)
    print(f"\ncorpus: {len(list(CORPUS.glob('bip-*/meta.json')))} kept, {len(excluded)} dropped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
