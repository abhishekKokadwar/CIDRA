"""The Pythons CIDRA claims to support (PyPI classifiers, the README badge, the
requires-python floor) are exactly the ones CI runs the tests on."""

import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.mark.req("COMPAT")
def test_every_python_cidra_advertises_is_tested_in_ci():
    jobs = yaml.safe_load((ROOT / ".github/workflows/test-cidra.yml").read_text(encoding="utf-8"))["jobs"]
    tested = {str(m["python"]) for m in jobs["compat"]["strategy"]["matrix"]["include"]}
    tested |= {str(s["with"]["python-version"]) for s in jobs["unit"]["steps"] if "setup-python" in s.get("uses", "")}
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    classifiers = set(re.findall(r"Programming Language :: Python :: (3\.\d+)", pyproject))
    badge = set(re.search(r"img\.shields\.io/badge/python-([^-]+)-", (ROOT / "README.md").read_text(encoding="utf-8"))
                .group(1).split("%20%7C%20"))
    floor = re.search(r'requires-python = ">=(3\.\d+)"', pyproject).group(1)
    assert classifiers == tested and badge == tested
    assert floor == min(tested, key=lambda v: int(v.split(".")[1]))
