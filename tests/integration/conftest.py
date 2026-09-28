"""Everything under tests/integration needs a running Docker daemon.

Auto-marks these tests `docker` so `pytest -m "not docker"` skips the whole
directory without touching individual test functions.
"""

from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items):
    for item in items:
        # Only mark tests that actually live in this integration directory.
        if _HERE in Path(str(item.fspath)).resolve().parents:
            item.add_marker(pytest.mark.docker)
