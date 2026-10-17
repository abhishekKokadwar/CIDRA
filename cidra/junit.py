"""Per-test results from pytest's JUnit XML report.

The sandbox test command asks pytest for the report (sandbox_test_command), so
every test run leaves one at limits.JUNIT. Reading it gives each test's outcome
before and after a patch, instead of only the FAILED lines that fit in the
16 KB output tail.
"""

import xml.etree.ElementTree as ET
from typing import Optional

from cidra.sandbox import limits

# A child element that marks a test's outcome; no such child means it passed.
_OUTCOMES = (("failure", "failed"), ("error", "error"), ("skipped", "skipped"))


def parse(xml: bytes) -> dict[str, str]:
    """{"<classname>::<name>": "passed" | "failed" | "error" | "skipped"}.

    The report is written by the repository's own test run, so it is untrusted:
    read with ElementTree (no external entities) and size-capped by the caller.
    A report that does not parse yields no results rather than an exception.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return {}
    results = {}
    for case in root.iter("testcase"):
        test_id = f"{case.get('classname', '')}::{case.get('name', '')}"
        results[test_id] = next((o for tag, o in _OUTCOMES if case.find(tag) is not None), "passed")
    return results


def read(session) -> Optional[dict[str, str]]:
    """The last test run's per-test results, or None when there is no report
    (a test command that is not pytest, or a run that never started)."""
    raw = session.read_file(limits.JUNIT)
    return parse(raw) if raw else None
