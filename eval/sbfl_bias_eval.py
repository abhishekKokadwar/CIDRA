"""Phase 8 eval: SBFL localization is input-order-independent.

The paper claim: mathematical suspiciousness ranking removes the LLM's
input-order bias. This measures it directly — for each scenario, shuffle the
element order many times and confirm the buggy element's rank never moves.

A prompt-only baseline (favour-first-file) is included for contrast: it "localizes"
whatever appears first, so its accuracy collapses under shuffling. SBFL does not.

No LLM, no Docker — this is a property of the ranker. Run:
    python eval/sbfl_bias_eval.py
"""

import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from cidra.nodes.sbfl import Spectrum, rank  # noqa: E402

# (name, spectra, the element that is actually buggy)
SCENARIOS = [
    ("single-fault", [
        Spectrum("src/calc.py::add", ef=4, ep=0, total_failing=4, total_passing=6),
        Spectrum("src/util.py::log", ef=1, ep=6, total_failing=4, total_passing=6),
        Spectrum("src/io.py::read",  ef=0, ep=6, total_failing=4, total_passing=6),
        Spectrum("src/calc.py::sub", ef=2, ep=5, total_failing=4, total_passing=6),
    ], "src/calc.py::add"),
    ("shared-lines", [
        Spectrum("a::f", ef=3, ep=1, total_failing=3, total_passing=5),
        Spectrum("b::g", ef=3, ep=0, total_failing=3, total_passing=5),  # buggy: no passing
        Spectrum("c::h", ef=2, ep=5, total_failing=3, total_passing=5),
    ], "b::g"),
    ("many-elements", [
        Spectrum(f"m{i}", ef=(5 if i == 7 else 1), ep=(0 if i == 7 else 5),
                 total_failing=5, total_passing=8) for i in range(12)
    ], "m7"),
]

SHUFFLES = 100


def _favour_first(spectra):
    """Prompt-only baseline: 'localize' the first element presented."""
    return spectra[0].element


def main() -> int:
    print("\nSBFL input-order bias eval\n")
    sbfl_ok = base_ok = total = 0
    for name, spectra, buggy in SCENARIOS:
        s_hits = b_hits = 0
        for _ in range(SHUFFLES):
            shuffled = spectra[:]
            random.shuffle(shuffled)
            if rank(shuffled)[0][0] == buggy:
                s_hits += 1
            if _favour_first(shuffled) == buggy:
                b_hits += 1
        total += SHUFFLES
        sbfl_ok += s_hits
        base_ok += b_hits
        print(f"  {name:<16} SBFL top-1 {s_hits}/{SHUFFLES}   "
              f"prompt-first baseline {b_hits}/{SHUFFLES}")
    print(f"\n  SBFL accuracy under shuffling:          {100*sbfl_ok//total}%")
    print(f"  prompt-first baseline under shuffling:  {100*base_ok//total}%")
    ok = sbfl_ok == total  # SBFL must be perfectly order-independent
    print(f"\n  {'PASS' if ok else 'FAIL'}: SBFL localizes the fault regardless of order\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
