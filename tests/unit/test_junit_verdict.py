"""The verdict is judged from pytest's per-test report, which lists every test;
the log's FAILED lines, cut to a 16 KB tail, decide only when there is no
report (KNOWN_GAPS G-25)."""

from types import SimpleNamespace

import pytest

from cidra import junit
from cidra.nodes.fix import judge_verification

pytestmark = pytest.mark.req("G-25")

STATE = {"target_tests": ["tests/test_calc.py::test_add"], "repro_failing_tests": ["tests.test_calc::test_add"]}


def _run(exit_code=1, log="1 failed"):
    return SimpleNamespace(passed=exit_code == 0, exit_code=exit_code, timed_out=False, stdout_tail=log, stderr_tail="")


def test_a_regression_the_log_tail_lost_still_blocks_verification():
    # The log's tail kept only unrelated lines; the report has every test.
    report = {"tests.test_calc::test_add": "passed", "tests.test_other::test_sub": "failed"}
    verified, _, regressions, note = judge_verification(STATE, _run(log="... 400 lines cut ...\n1 failed"), report)
    assert not verified and regressions == ["tests.test_other::test_sub"], note


def test_the_target_still_failing_in_the_report_is_not_verified():
    report = {"tests.test_calc::test_add": "failed"}
    verified, still, _, note = judge_verification(STATE, _run(log="1 failed"), report)
    assert not verified and still == ["tests.test_calc::test_add"] and "still failing" in note


def test_without_a_report_the_log_decides():
    log = "FAILED tests/test_calc.py::test_add - assert -1 == 3\n1 failed"
    verified, _, _, note = judge_verification(STATE, _run(log=log), None)
    assert not verified and "still failing" in note


def test_log_and_report_ids_name_the_same_test():
    assert junit.same_test("tests/test_calc.py::test_add", "tests.test_calc::test_add")
    assert junit.same_test("sub/tests/test_a.py::TestX::test_y[1]", "tests.test_a.TestX::test_y[1]")
    assert not junit.same_test("tests/test_calc.py::test_add", "tests.test_calc::test_sub")
    assert junit.junit_id("tests.test_a.TestX::test_y") == "tests.test_a.TestX::test_y"  # already in report form


def test_a_collection_error_is_named_by_its_module_and_counts_as_a_failure():
    xml = (b'<testsuites><testsuite><testcase classname="" name="tests.test_api">'
           b'<error message="collection failure"/></testcase></testsuite></testsuites>')
    report = junit.parse(xml)
    assert report == {"tests.test_api": "error"}
    assert junit.failures(report, "") == ["tests.test_api"]
    assert junit.same_test("tests/test_api.py", "tests.test_api")


def test_an_unreadable_report_falls_back_to_the_log():
    session = SimpleNamespace(read_file=lambda path: b"<testsuites><testcase")
    assert junit.read(session) is None
    assert junit.failures(None, "FAILED tests/test_a.py::test_x - boom") == ["tests/test_a.py::test_x"]


def test_a_parametrized_id_with_spaces_is_read_whole_and_matches_the_report():
    # thefuck-1 and -25 (corpus v5): the log id was cut at its first space, so the
    # report's full id no longer matched and a real failure read as "not the CI failure".
    from cidra.nodes.ingest import failing_tests
    log = ("FAILED tests/rules/test_pip_unknown_command.py::test_get_new_command[pip un+install thefuck-un+install]\n"
           "FAILED tests/rules/test_mkdir_p.py::test_get_new_command[command1-hdfs dfs -mkdir -p foo/bar/baz] - assert 'a' == 'b'\n"
           "FAILED tests/test_calc.py::test_add - assert -1 == 3")
    ids = failing_tests(log)
    assert ids == ["tests/rules/test_pip_unknown_command.py::test_get_new_command[pip un+install thefuck-un+install]",
                   "tests/rules/test_mkdir_p.py::test_get_new_command[command1-hdfs dfs -mkdir -p foo/bar/baz]",
                   "tests/test_calc.py::test_add"]
    assert junit.same_test(ids[1], "tests.rules.test_mkdir_p::test_get_new_command[command1-hdfs dfs -mkdir -p foo/bar/baz]")


def test_a_log_id_cut_inside_its_parameters_still_matches_its_test():
    full = "tests.rules.test_mkdir_p::test_get_new_command[command1-hdfs dfs -mkdir -p foo/bar/baz]"
    assert junit.same_test("tests/rules/test_mkdir_p.py::test_get_new_command[command1-hdfs", full)
    assert not junit.same_test("tests/rules/test_mkdir_p.py::test_get_new_command[command2-./bin", full)
    assert not junit.same_test("tests/rules/test_mkdir_p.py::test_other[command1-hdfs", full)
