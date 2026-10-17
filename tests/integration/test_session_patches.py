"""Each fix attempt is verified on the failing commit plus its own diff only (KNOWN_GAPS G-15).

Needs Docker and the sandbox image (CI builds both); no practice repo.
"""

import pathlib
import tempfile

import pytest

from cidra.sandbox.runner import Session, client

pytestmark = pytest.mark.req('R6')

try:
    client().ping()
except Exception:  # noqa: BLE001 - no daemon, no image: nothing to test here
    pytest.skip("Docker is not available", allow_module_level=True)


def _source() -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp(prefix="cidra_src_"))
    (d / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    return d


# Attempt 1 applies but is wrong; attempt 2 is written against the original file.
ATTEMPT_1 = "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a * b\n"
ATTEMPT_2 = "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"


def test_a_later_attempt_starts_from_the_original_checkout():
    with Session(_source()) as s:
        assert s.apply_patch(ATTEMPT_1).passed
        second = s.apply_patch(ATTEMPT_2)
        assert second.passed, second.stdout_tail or second.stderr_tail
        shown = s.run("test", "cat calc.py")
    assert shown.stdout_tail == "def add(a, b):\n    return a + b\n"


def test_a_failed_apply_leaves_the_last_good_tree_alone():
    with Session(_source()) as s:
        assert not s.apply_patch("--- a/nope.py\n+++ b/nope.py\n@@ -1 +1 @@\n-x\n+y\n").passed
        assert s.apply_patch(ATTEMPT_2).passed
        shown = s.run("test", "cat calc.py")
    assert "a + b" in shown.stdout_tail


def test_a_reinstall_replaces_the_packages_of_the_last_install():
    # `--target <site>` is appended to the command, so "$2" is the site directory.
    first = "sh -c 'mkdir -p \"$2\" && touch \"$2/first\"' sh"
    second = "sh -c 'mkdir -p \"$2\" && touch \"$2/second\"' sh"
    with Session(_source()) as s:
        assert s.install(first).passed
        assert s.install(second).passed
        listed = s.run("test", "ls /home/cidra/site")
    assert listed.stdout_tail.split() == ["second"]
