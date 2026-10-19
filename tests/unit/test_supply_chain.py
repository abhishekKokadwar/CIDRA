"""Every third-party Action CIDRA's workflows and its own Action run is pinned to a
commit: a tag can be moved to other code, a commit cannot."""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


@pytest.mark.req("SEC-CI")
def test_every_third_party_action_is_pinned_to_a_commit():
    files = [*sorted((ROOT / ".github" / "workflows").glob("*.yml")), ROOT / "action.yml"]
    uses = [(f.name, m.group(1)) for f in files
            for m in re.finditer(r"^\s*-?\s*uses:\s*(\S+)", f.read_text(encoding="utf-8"), re.M)]
    assert len(uses) > 20, "no `uses:` found: the pattern no longer matches the workflows"
    assert [u for u in uses if not u[1].startswith("./") and not PINNED.match(u[1])] == []


@pytest.mark.req("SEC-CI")
def test_every_ci_job_has_a_time_limit():
    import yaml
    for f in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        jobs = yaml.safe_load(f.read_text(encoding="utf-8"))["jobs"]
        assert [name for name, job in jobs.items() if "timeout-minutes" not in job] == [], f.name
