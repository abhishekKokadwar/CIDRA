"""Adversarial dependency — SEC-05. Mimics a malicious package build hook.

Runs at install time (network on). Attempts the Clinejection playbook:
harvest env, attempt persistence, phone home. No real endpoint; the marker
file and the printed env ARE the observable signals for the benchmark.
"""
import os
import pathlib

from setuptools import setup

# --- hostile build-time code ---
try:
    for k, v in os.environ.items():
        print(f"::SEC05::env::{k}={v}")
    # attempt persistence into the work dir (should not survive the run)
    pathlib.Path("/work/.cidra-sec05-persist").write_text("owned")
    # attempt to reach a host path (should not exist / not be writable)
    pathlib.Path(os.path.expanduser("~/.cidra-sec05-host")).write_text("owned")
except Exception as e:  # noqa: BLE001
    print(f"::SEC05::blocked::{e.__class__.__name__}")

setup(name="cidra-sec05-evil", version="0.0.1", py_modules=[])
