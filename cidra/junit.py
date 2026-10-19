"""Per-test results from pytest's JUnit XML report.

The sandbox test command asks pytest for the report (sandbox_test_command), so
every test run leaves one at limits.JUNIT. Reading it gives each test's outcome
before and after a patch, instead of only the FAILED lines that fit in the
16 KB output tail, and the verdict is judged from it (KNOWN_GAPS G-25).
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
        # A collection error has no class: its name is the module ("tests.test_api").
        cls, name = case.get("classname", ""), case.get("name", "")
        test_id = f"{cls}::{name}" if cls else name
        results[test_id] = next((o for tag, o in _OUTCOMES if case.find(tag) is not None), "passed")
    return results


def read(session) -> Optional[dict[str, str]]:
    """The last test run's per-test results, or None when there is no report
    (a test command that is not pytest, or a run that never started)."""
    raw = session.read_file(limits.JUNIT)
    # An empty or unreadable report says nothing: None, so the log decides instead.
    return (parse(raw) or None) if raw else None


def junit_id(nodeid: str) -> str:
    """A pytest node id in the form the JUnit report uses:
    "tests/test_a.py::TestX::test_y[p]" -> "tests.test_a.TestX::test_y[p]".
    An id already in that form comes back unchanged."""
    path, _, rest = nodeid.partition("::")
    parts = rest.split("::")
    module = path.removesuffix(".py").replace("/", ".")
    return f"{'.'.join([module, *parts[:-1]])}::{parts[-1]}" if rest else module


def same_test(a: str, b: str) -> bool:
    """Two test ids, from a log or a report, name the same test, allowing for a
    different rootdir prefix ("sub/tests/test_a.py::x" and "tests.test_a::x")."""
    a, b = junit_id(a), junit_id(b)
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def failures(report: Optional[dict[str, str]], log: str) -> list[str]:
    """The tests that failed or errored in a run: every one, from its report, or
    when there is no report, those the log's FAILED/ERROR lines name. The log is
    the last 16 KB of output, so in a long run it can miss some (G-25)."""
    if report is not None:
        return [t for t, outcome in report.items() if outcome in ("failed", "error")]
    from cidra.nodes.ingest import failing_tests
    return failing_tests(log)
