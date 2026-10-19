"""Per-test results before and after a patch, through the real nodes and sandbox
(ROADMAP M1). Needs Docker and the sandbox image (CI builds both)."""

import pathlib
import re

import pytest

from cidra.nodes.environment import close_session, prepare_sandbox, session_for
from cidra.nodes.fix import verify_fix
from cidra.nodes.reproduce import reproduce_once
from cidra.sandbox.runner import client

pytestmark = pytest.mark.req('M1-JUNIT', 'R7')

try:
    client().ping()
except Exception:  # noqa: BLE001 - no daemon, no image: nothing to test here
    pytest.skip("Docker is not available", allow_module_level=True)

FIX = ("--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n"
       "-    return a - b\n+    return a + b\n")


@pytest.fixture
def state(tmp_path: pathlib.Path):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text(
        "import pytest\nfrom calc import add\n\n\n"
        "def test_add():\n    assert add(1, 2) == 3\n\n\n"
        "def test_zero():\n    assert add(0, 0) == 0\n\n\n"
        "@pytest.mark.skip(reason='later')\ndef test_later():\n    pass\n")
    s = {"run_id": "it-junit", "source_dir": str(tmp_path),
         "test_command": "cd /work && python -m pytest -q 2>&1",  # behind a cd on purpose
         "ci_failing_tests": ["tests/test_calc.py::test_add"]}
    # The exact image for the evidence block: its tag and its content digest.
    assert re.fullmatch(r"cidra-sandbox:[\w.]+@sha256:[0-9a-f]{64}", prepare_sandbox(s)["image_tag"])
    yield s
    close_session("it-junit")


def test_each_tests_outcome_is_recorded_before_and_after_the_patch(state):
    before = reproduce_once(state)
    assert before["reproduced"], before.get("analysis_error")
    assert before["repro_junit"] == {
        "tests.test_calc::test_add": "failed",
        "tests.test_calc::test_zero": "passed",
        "tests.test_calc::test_later": "skipped",
    }

    assert session_for("it-junit").apply_patch(FIX).passed
    after = verify_fix({**state, **before, "patch_applied": True})
    assert after["verified"], after.get("verify_note")
    assert after["verify_junit"] == {
        "tests.test_calc::test_add": "passed",
        "tests.test_calc::test_zero": "passed",
        "tests.test_calc::test_later": "skipped",
    }


@pytest.mark.req("G-25")
def test_the_verdict_holds_when_the_log_tail_drops_the_target_and_the_regression(tmp_path):
    # 400 already-failing tests with long ids run last, so the log's 16 KB tail
    # holds only their FAILED lines: the target and the test the patch breaks are
    # in the per-test report alone.
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n\n\ndef sub(a, b):\n    return a - b\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text(
        "from calc import add, sub\n\n\n"
        "def test_add():\n    assert add(1, 2) == 3\n\n\n"
        "def test_sub():\n    assert sub(3, 1) == 2\n")
    (tmp_path / "tests" / "test_zz_noise.py").write_text(
        "import pytest\n\n\n@pytest.mark.parametrize('case', ['an-already-failing-case-with-a-long-name-%03d' % i for i in range(400)])\n"
        "def test_noise(case):\n    assert False\n")
    s = {"run_id": "it-junit-tail", "source_dir": str(tmp_path), "test_command": "cd /work && python -m pytest -q 2>&1",
         "ci_failing_tests": ["tests/test_calc.py::test_add"]}
    prepare_sandbox(s)
    try:
        before = reproduce_once(s)
        assert before["reproduced"], before.get("analysis_error")
        assert "test_add" not in before["repro_results"][-1].stdout_tail  # the log alone could not show it
        # Fixes add, and breaks sub (a test that passed before).
        breaks_sub = ("--- a/calc.py\n+++ b/calc.py\n@@ -1,6 +1,6 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"
                      " \n \n def sub(a, b):\n-    return a - b\n+    return a + b\n")
        assert session_for("it-junit-tail").apply_patch(breaks_sub).passed
        after = verify_fix({**s, **before, "patch_applied": True})
        assert not after["verified"] and after["regressions"] == ["tests.test_calc::test_sub"], after.get("verify_note")
    finally:
        close_session("it-junit-tail")


def test_a_missing_or_oversized_report_reads_as_none(state):
    session = session_for("it-junit")
    assert session.read_file("/home/cidra/no-such-file") is None
    session.run("test", "head -c 2000 /dev/zero > /home/cidra/big")
    assert session.read_file("/home/cidra/big", max_bytes=1000) is None
    assert session.read_file("/home/cidra/big") == b"\0" * 2000
