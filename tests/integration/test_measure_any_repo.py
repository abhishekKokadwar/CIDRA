"""eval/measure.py on a repository that is not the practice repo.

Builds a throwaway git repo with a failing commit and its fix, describes it with
the fixture format (repo_url, both commits, a stored log, its own install and
test commands, a Python version), and runs the harness on the stub model.
No network beyond the dependency install, no GitHub token, no model.
"""

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

LOG = """============================= test session starts ==============================
collected 2 items

checks/test_mathx.py F                                                   [ 50%]
checks/test_other.py .                                                   [100%]

=================================== FAILURES ===================================
_________________________________ test_double __________________________________

    def test_double():
>       assert double(3) == 6
E       assert 5 == 6
E        +  where 5 = double(3)

checks/test_mathx.py:5: AssertionError
=========================== short test summary info ============================
FAILED checks/test_mathx.py::test_double - assert 5 == 6
========================= 1 failed, 1 passed in 0.02s ==========================
"""

ANSWERS = {
    "Analysis": {
        "category": "assertion_error", "confidence": 0.95,
        "evidence": "assert 5 == 6: double(3) returns 5.",
        "proposed_action": "Multiply instead of adding.",
        "failing_test": "checks/test_mathx.py::test_double",
    },
    "Patch": {
        "diff": "--- a/pkg/mathx.py\n+++ b/pkg/mathx.py\n@@ -1,2 +1,2 @@\n def double(x):\n-    return x + 2\n+    return x * 2\n",
        "target_file": "pkg/mathx.py",
        "rationale": "double added 2 instead of multiplying by 2.",
    },
}


def _git(repo, *args):
    subprocess.check_call(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
                           "-c", "commit.gpgsign=false", *args], stdout=subprocess.DEVNULL)


def _make_repo(repo: pathlib.Path) -> None:
    files = {
        "deps.txt": "six\n",
        "pkg/__init__.py": "",
        "pkg/mathx.py": "def double(x):\n    return x + 2\n",
        "checks/test_mathx.py": "from pkg.mathx import double\n\n\ndef test_double():\n    assert double(3) == 6\n",
        "checks/test_other.py": "import six\n\n\ndef test_ok():\n    assert six.PY3\n",
    }
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text, encoding="utf-8", newline="\n")
    subprocess.check_call(["git", "init", "--quiet", str(repo)])
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "bug")
    (repo / "pkg/mathx.py").write_text("def double(x):\n    return x * 2\n", encoding="utf-8", newline="\n")
    (repo / "checks/test_mathx.py").write_text(
        "from pkg.mathx import double\n\n\ndef test_double():\n    assert double(3) == 6\n\n\n"
        "def test_double_more():\n    assert double(5) == 10\n    assert double(0) == 0\n",
        encoding="utf-8", newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "fix")


def _fixture(corpus: pathlib.Path, fid: str, repo: pathlib.Path, held_out_paths: list[str]) -> None:
    folder = corpus / fid
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({
        "class": "assertion_error",
        "repo_url": str(repo),
        "failing_ref": "HEAD~1",
        "fix_ref": "HEAD",
        "held_out_paths": held_out_paths,
        "install_command": "pip install --quiet -r deps.txt",
        "test_command": "python -m pytest -q checks 2>&1",
        "python_version": "3.12",
    }), encoding="utf-8")
    (folder / "expected.json").write_text(json.dumps({
        "expected_outcome": "verified_fix", "expected_analysis": {"category": "assertion_error"},
    }), encoding="utf-8")
    (folder / "raw.log").write_text(LOG, encoding="utf-8")
    (folder / "fake_llm.json").write_text(json.dumps(ANSWERS), encoding="utf-8")


def test_harness_measures_a_repo_from_its_fixture_alone(tmp_path):
    repo, corpus, out = tmp_path / "repo", tmp_path / "corpus", tmp_path / "out.json"
    _make_repo(repo)
    # The fix commit's version of the failing test file: fails on the bug, so it can judge.
    _fixture(corpus, "judged", repo, ["checks/test_mathx.py"])
    # A file the fix did not touch: passes on the bug too, so it proves nothing.
    _fixture(corpus, "unjudged", repo, ["checks/test_other.py"])

    env = {**os.environ, "CIDRA_WORKTREE_ROOT": str(tmp_path / "wt"),
           "CIDRA_GITHUB_TOKEN": "", "CIDRA_GITHUB_TOKEN_RO": "", "CIDRA_PRACTICE_REPO": str(tmp_path / "absent")}
    done = subprocess.run([sys.executable, str(ROOT / "eval" / "measure.py"), "--stub",
                           "--corpus", str(corpus), "--out", str(out)],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]

    result = json.loads(out.read_text(encoding="utf-8"))
    runs = {r["fixture"]: r for r in result["runs"]}
    for r in runs.values():
        assert r["outcome"] == "verified_fix", r
        assert r["python_version"] == "3.12"
        assert r["requests"] == 2
    assert runs["judged"]["held_out_valid"] is True and runs["judged"]["held_out"]["passed"] is True
    assert runs["unjudged"]["held_out_valid"] is False
    assert result["summary"]["false_verified"] == "0/1 (0%)"
    assert result["summary"]["false_verified_excluded"] == ["unjudged"]
