"""reports/RESULTS.md states exactly what the committed result files say: its
table is eval/results_table.py's output, so no number in it can be typed in by
hand or drift from the runs."""

import pathlib

import pytest

from eval.results_table import table

ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.mark.req("RESULTS-REPORT")
def test_the_results_report_is_computed_from_the_result_files():
    report = (ROOT / "reports" / "RESULTS.md").read_text(encoding="utf-8")
    assert table() in report
    for link in [part.split(")")[0] for part in report.split("](../")[1:]]:
        assert (ROOT / link.split("#")[0]).exists(), link
