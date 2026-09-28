"""Phase 8.2 / 8.4 — SBFL math + input-order invariance (the bias test)."""

import random

from cidra.nodes.sbfl import (Spectrum, ochiai, tarantula, rank,
                              build_spectra, format_for_prompt)


def test_ochiai_pure_fault_scores_one():
    # executed by every failing test, no passing test => perfectly suspicious
    s = Spectrum("buggy", ef=3, ep=0, total_failing=3, total_passing=4)
    assert ochiai(s) == 1.0


def test_ochiai_innocent_line_scores_zero():
    # never executed by a failing test
    s = Spectrum("innocent", ef=0, ep=4, total_failing=3, total_passing=4)
    assert ochiai(s) == 0.0


def test_ochiai_partial_between_zero_and_one():
    s = Spectrum("shared", ef=2, ep=2, total_failing=3, total_passing=4)
    assert 0.0 < ochiai(s) < 1.0


def test_tarantula_ranks_fault_above_shared():
    fault = Spectrum("fault", ef=3, ep=0, total_failing=3, total_passing=3)
    shared = Spectrum("shared", ef=3, ep=3, total_failing=3, total_passing=3)
    assert tarantula(fault) > tarantula(shared)


def test_build_spectra_from_coverage():
    coverage = {
        "t_ok":  {"add": True,  "sub": False},
        "t_bad": {"add": True,  "sub": True},
    }
    outcomes = {"t_ok": True, "t_bad": False}
    spectra = {s.element: s for s in build_spectra(coverage, outcomes)}
    # "sub" is executed only by the failing test -> more suspicious than "add"
    assert ochiai(spectra["sub"]) > ochiai(spectra["add"])


def test_ranking_is_input_order_independent():
    """THE BIAS TEST (exit criterion): the buggy element ranks #1 regardless of the
    order elements are presented in. Shuffle many times; the top never changes."""
    base = [
        Spectrum("src/calc.py::add", ef=3, ep=0, total_failing=3, total_passing=5),  # fault
        Spectrum("src/util.py::log", ef=1, ep=5, total_failing=3, total_passing=5),
        Spectrum("src/io.py::read",  ef=0, ep=5, total_failing=3, total_passing=5),
        Spectrum("src/calc.py::sub", ef=2, ep=4, total_failing=3, total_passing=5),
    ]
    tops = set()
    for _ in range(50):
        shuffled = base[:]
        random.shuffle(shuffled)
        tops.add(rank(shuffled)[0][0])
    assert tops == {"src/calc.py::add"}  # same #1 every time, order-independent


def test_ties_break_deterministically():
    a = Spectrum("z", ef=2, ep=2, total_failing=3, total_passing=3)
    b = Spectrum("a", ef=2, ep=2, total_failing=3, total_passing=3)  # identical score
    assert [e for e, _ in rank([a, b])] == ["a", "z"]  # name-sorted, stable


def test_format_for_prompt_shows_only_suspicious():
    ranking = [("fault", 0.9), ("innocent", 0.0)]
    out = format_for_prompt(ranking)
    assert "fault" in out and "innocent" not in out
    assert format_for_prompt([("x", 0.0)]) == ""  # nothing suspicious -> empty
