"""CI retries the steps that download (a network hiccup is not a broken build) and
never the steps that test (a test that passes on a second try is flaky, and fails)."""

import pathlib
import re
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RETRY = str(ROOT / "scripts" / "retry.sh")
DOWNLOADS = re.compile(r"^(git clone|docker build|npm ci|npx playwright install)\b")
TESTS = re.compile(r"\b(pytest|vitest|playwright test|measure\.py|run_adversarial|run_benchmark|smoke_installed)\b")
pytestmark = pytest.mark.req("CI-NET")


def _commands():
    files = [*(ROOT / ".github" / "workflows").glob("*.yml"), ROOT / "scripts" / "smoke_installed.sh"]
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            command = re.sub(r"^\s*(- )?(run: )?", "", line)
            yield f.name, command, re.sub(r'^bash \S*retry\.sh"? ', "", command)


def test_every_download_step_retries_and_no_test_step_does():
    commands = list(_commands())
    downloads = [(f, c) for f, c, bare in commands if DOWNLOADS.match(bare)]
    assert len(downloads) >= 9, "the download pattern no longer matches the workflows"
    assert [(f, c) for f, c in downloads if "retry.sh" not in c] == []
    assert [(f, c) for f, c, _ in commands if "retry.sh" in c and TESTS.search(c)] == []


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="CI runs it under Linux bash")
def test_retry_succeeds_after_two_failures_and_gives_up_after_three(tmp_path):
    flaky = 'n=$(cat count 2>/dev/null || echo 0); echo $((n+1)) > count; [ "$n" -ge 2 ]'
    run = lambda *cmd: subprocess.run(["bash", RETRY, *cmd], cwd=tmp_path, env={"RETRY_DELAY": "0", "PATH": "/usr/bin:/bin"},  # noqa: E731
                                      capture_output=True, text=True)
    ok = run("bash", "-c", flaky)
    assert ok.returncode == 0 and ok.stdout.count("::warning::") == 2
    (tmp_path / "count").unlink()
    broken = run("bash", "-c", "exit 7")
    assert broken.returncode == 7 and "::error::failed 3 times" in broken.stdout
