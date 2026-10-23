"""The model proposes text edits and CIDRA builds the diff (15 of 19 hand-written
diffs on the BugsInPy corpus did not apply). The diff must apply with `git apply`,
and an edit that cannot be placed must say why, for the model's next attempt."""

import subprocess

import pytest

from cidra.nodes import fix
from cidra.nodes.fix import Edit, edits_to_diff
from scripts.fake_llm import diff_to_edits

pytestmark = pytest.mark.req('R4')

CALC = "def add(a, b):\n    return a - b\n\n\ndef sub(a, b):\n    return a - b\n"


def _repo(tmp_path, files):
    for path, text in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_bytes(text.encode())
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def _applies(repo, diff):
    (repo / "fix.patch").write_text(diff, encoding="utf-8", newline="")
    return subprocess.run(["git", "apply", "--check", "fix.patch"], cwd=repo, capture_output=True).returncode == 0


def test_edits_become_a_diff_that_applies(tmp_path):
    repo = _repo(tmp_path, {"src/calc.py": CALC, "requirements.txt": "pytest", "win.py": "a = 1\r\nb = 2\r\n"})
    diff = edits_to_diff([
        Edit(path="src/calc.py", old="def add(a, b):\n    return a - b", new="def add(a, b):\n    return a + b"),
        Edit(path="requirements.txt", old="", new="requests\n"),  # appended; the file had no final newline
        Edit(path="win.py", old="b = 2\n", new="b = 3\n"),  # CRLF file, LF edit
        Edit(path="src/new.py", old="", new="X = 1\n"),
    ], repo)
    assert "+    return a + b" in diff and "+requests" in diff and "--- /dev/null" in diff
    assert _applies(repo, diff), diff


def test_an_edit_that_cannot_be_placed_says_why(tmp_path):
    repo = _repo(tmp_path, {"src/calc.py": CALC})
    with pytest.raises(ValueError, match="was not found in src/calc.py"):
        edits_to_diff([Edit(path="src/calc.py", old="return a * b", new="x")], repo)
    with pytest.raises(ValueError, match="appears 2 times"):
        edits_to_diff([Edit(path="src/calc.py", old="    return a - b", new="x")], repo)
    for path in ("../outside.py", "/etc/passwd", "."):
        with pytest.raises(ValueError, match="not a file in the repository"):
            edits_to_diff([Edit(path=path, old="", new="x")], repo)


def test_generate_fix_reports_unplaceable_edits_and_the_retry_quotes_them(tmp_path, monkeypatch):
    repo = _repo(tmp_path, {"src/calc.py": CALC})
    seen = []

    def fake_structured(**kwargs):
        seen.append(kwargs["user"])
        return fix.Patch(edits=[Edit(path="src/calc.py", old="not in the file", new="x")], rationale="r")

    monkeypatch.setattr(fix, "structured", fake_structured)
    monkeypatch.setattr(fix, "session_for", lambda _run_id: None)
    state = {"run_id": "r", "source_dir": str(repo), "error_region": "e"}
    out = fix.generate_fix(state)
    assert out["fix_diff"] is None and out["patch_applied"] is False
    assert "was not found in src/calc.py" in out["apply_error"]
    fix.generate_fix({**state, **out})
    assert "could not be applied" in seen[-1] and "not in the file" in seen[-1]


def test_stub_turns_reference_diffs_into_edits_that_rebuild_them(tmp_path):
    repo = _repo(tmp_path, {"src/calc.py": CALC})
    reference = ("--- a/src/calc.py\n+++ b/src/calc.py\n@@ -1,3 +1,3 @@\n def add(a, b):\n"
                 "-    return a - b\n+    return a + b\n \n")
    edits = [Edit(**e) for e in diff_to_edits(reference)]
    assert [e.path for e in edits] == ["src/calc.py"]
    assert _applies(repo, edits_to_diff(edits, repo))


def test_edits_sent_as_json_text_are_read_as_the_list():
    # corpus v8, keras-27: the model put the edits list in a string, and the attempt was lost
    args = '{"edits": "[{\\"path\\": \\"a.py\\", \\"old\\": \\"x\\", \\"new\\": \\"y\\"}]", "rationale": "r"}'
    assert fix.Patch.model_validate_json(args).edits == [Edit(path="a.py", old="x", new="y")]
    with pytest.raises(ValueError):
        fix.Patch.model_validate_json('{"edits": "not json", "rationale": "r"}')
