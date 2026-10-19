"""The package check catches the wheels that broke or would break `pip install cidra`."""

import zipfile

import pytest

from scripts.check_package import problems

pytestmark = pytest.mark.req("PKG")

PAGE = '<script type="module" src="/assets/index-new.js"></script><link rel="stylesheet" href="/assets/index-new.css">'


def _wheel(tmp_path, version="1.2.3", page=PAGE, extra=(), drop=()):
    files = {
        "cidra-1.2.3.dist-info/METADATA": f"Metadata-Version: 2.1\nName: cidra\nVersion: {version}\n",
        "cidra/sandbox/Dockerfile": "FROM python:3.11-slim\n",
        "cidra/static/index.html": page,
        "cidra/static/assets/index-new.js": 'const v="1.2.3";',
        "cidra/static/assets/index-new.css": "body{}",
        **{name: "x" for name in extra},
    }
    path = tmp_path / "cidra.whl"
    with zipfile.ZipFile(path, "w") as z:
        for name, text in files.items():
            if name not in drop:
                z.writestr(name, text)
    return str(path)


def test_a_complete_wheel_passes(tmp_path):
    assert problems(_wheel(tmp_path), "1.2.3") == []


def test_a_wheel_without_the_dockerfile_fails(tmp_path):  # cidra 0.2.0 on PyPI
    assert problems(_wheel(tmp_path, drop={"cidra/sandbox/Dockerfile"}), "1.2.3") == [
        "cidra/sandbox/Dockerfile is missing: the sandbox image cannot be built from an install"]


def test_a_stale_bundle_left_by_an_earlier_build_fails(tmp_path):  # a reused build/ directory
    found = problems(_wheel(tmp_path, extra={"cidra/static/assets/index-old.js"}), "1.2.3")
    assert found == ["cidra/static/assets/index-old.js is in the wheel but index.html does not load it (a stale build?)"]


def test_a_page_that_loads_a_missing_file_fails(tmp_path):
    found = problems(_wheel(tmp_path, drop={"cidra/static/assets/index-new.css"}), "1.2.3")
    assert found == ["index.html loads cidra/static/assets/index-new.css, which is not in the wheel"]


def test_a_version_mismatch_and_a_bundle_built_before_the_bump_fail(tmp_path):
    found = problems(_wheel(tmp_path, version="1.2.4"), "1.2.4")
    assert found == ["the dashboard bundle does not carry version 1.2.4: built before the version bump?"]
    assert problems(_wheel(tmp_path), "1.2.4")[0] == "wheel version is 1.2.3, pyproject.toml says 1.2.4"
