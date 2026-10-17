"""Per-test outcomes from pytest's JUnit report (ROADMAP M1)."""

from cidra import junit

REPORT = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="4">
  <testcase classname="tests.test_calc" name="test_add" time="0.01"><failure message="assert 1 == 2">x</failure></testcase>
  <testcase classname="tests.test_calc" name="test_sub[a b]" time="0.01"/>
  <testcase classname="tests.test_calc.TestX" name="test_y" time="0"><skipped message="later"/></testcase>
  <testcase classname="tests.test_io" name="test_open" time="0"><error message="fixture"/></testcase>
</testsuite></testsuites>"""


def test_each_test_gets_its_outcome():
    assert junit.parse(REPORT) == {
        "tests.test_calc::test_add": "failed",
        "tests.test_calc::test_sub[a b]": "passed",
        "tests.test_calc.TestX::test_y": "skipped",
        "tests.test_io::test_open": "error",
    }


def test_a_broken_report_gives_no_results_not_an_exception():
    assert junit.parse(b"<testsuites><testcase") == {}


def test_no_report_is_none():
    class Session:
        def read_file(self, path, max_bytes=0):
            assert path == "/home/cidra/junit.xml"
            return None

    assert junit.read(Session()) is None
