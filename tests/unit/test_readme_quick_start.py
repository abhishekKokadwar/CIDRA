"""The README quick start must keep working as action.yml changes (ROADMAP M4)."""

import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).parents[2]
pytestmark = pytest.mark.req("M4-QUICKSTART")


def _action():
    return yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))


def _quick_start_workflow():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Quick start", 1)[1].split("\n## ", 1)[0]
    block = re.search(r"```yaml\n(.*?)```", section, re.S).group(1)
    return yaml.safe_load(block)


def test_the_quick_start_passes_only_inputs_the_action_has():
    job = _quick_start_workflow()["jobs"]["repair"]
    step = next(s for s in job["steps"] if s.get("uses", "").startswith("abhishekKokadwar/CIDRA@"))
    assert set(step["with"]) <= set(_action()["inputs"])
    assert {"contents": "write", "pull-requests": "write", "actions": "read"}.items() <= job["permissions"].items()


def test_every_action_input_reaches_cidra():
    action = _action()
    runs = yaml.safe_dump(action["runs"])
    assert [name for name in action["inputs"] if not re.search(rf"inputs\.{name}\b", runs)] == []
