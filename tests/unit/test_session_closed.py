"""A sandbox session used outside its `with` block fails with a plain message,
not an AttributeError on None. No Docker needed: nothing is started."""

from pathlib import Path

import pytest

from cidra.sandbox.runner import Session


def test_a_session_that_is_not_open_says_so():
    session = Session(Path("."))
    with pytest.raises(RuntimeError, match="sandbox session is not open"):
        session.run("test", "pytest")
    with pytest.raises(RuntimeError, match="sandbox session is not open"):
        session.read_file("x.py")
