"""A repository nobody configured gets an install that fits it (ROADMAP M4)."""

import pytest

from cidra import config
from cidra.nodes.environment import detect_install, sandbox_install_command

pytestmark = pytest.mark.req("M4-INSTALL")


def _tree(tmp_path, **files):
    for name, text in files.items():
        (tmp_path / name.replace("__", "/")).write_text(text)
    return tmp_path


def test_requirements_files_come_first_with_their_dev_and_test_companions(tmp_path):
    tree = _tree(tmp_path, **{"requirements.txt": "", "requirements-dev.txt": "", "test-requirements.txt": "",
                              "pyproject.toml": "[project]\nname='x'\n"})
    assert detect_install(tree) == "pip install --quiet -r requirements.txt -r requirements-dev.txt -r test-requirements.txt"


def test_a_pyproject_package_installs_itself_with_its_test_extra(tmp_path):
    tree = _tree(tmp_path, **{"pyproject.toml": "[project]\nname='x'\n[project.optional-dependencies]\n"
                                                "docs=['sphinx']\ntesting=['hypothesis']\n"})
    assert detect_install(tree) == "pip install --quiet '.[testing]'"


def test_setup_py_or_a_pyproject_without_extras_installs_the_package(tmp_path):
    assert detect_install(_tree(tmp_path, **{"setup.py": "from setuptools import setup\nsetup()\n"})) == "pip install --quiet ."
    (tmp_path / "pyproject.toml").write_text("this is not toml [[[")
    assert detect_install(tmp_path) == "pip install --quiet ."  # unparseable: the package alone


def test_nothing_to_install_is_a_no_op(tmp_path):
    assert detect_install(tmp_path) == "true"


def test_an_explicit_command_always_wins(tmp_path, monkeypatch):
    tree = _tree(tmp_path, **{"requirements.txt": ""})
    monkeypatch.setattr(config, "INSTALL_COMMAND", None)
    assert sandbox_install_command({"source_dir": str(tree), "install_command": "pip install -e ."}) == "pip install -e ."
    monkeypatch.setattr(config, "INSTALL_COMMAND", "pip install poetry")
    assert sandbox_install_command({"source_dir": str(tree)}) == "pip install poetry"
