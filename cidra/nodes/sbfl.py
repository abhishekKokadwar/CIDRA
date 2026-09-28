"""Spectrum-Based Fault Localization. Phase 8.

Ranks program elements (files/methods/lines) by how *suspicious* they are of
causing the failure, computed from a coverage spectrum — which elements each
passing vs. failing test executed — BEFORE the LLM is prompted. The ranking is
fed to analyze as structured evidence, so the model reasons from a mathematical
suspiciousness order instead of favouring whichever file happens to appear first
in its context (input-order bias). That bias-independence is the Phase 8 exit
criterion and the paper's methodology claim.

Pure and deterministic: given the same spectrum it always yields the same order,
regardless of the order elements are supplied in (that invariance is tested).

Spectrum per element = four counts:
    ef  executed by failing tests
    ep  executed by passing tests
    nf  NOT executed by failing tests   (= total_failing - ef)
    np  NOT executed by passing tests   (= total_passing - ep)

Ochiai (default; strongest in the SBFL literature):
    ef / sqrt((ef + nf) * (ef + ep))
Tarantula (classic, offered for comparison):
    (ef/F) / ((ef/F) + (ep/P))
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Spectrum:
    """Coverage counts for one program element."""

    element: str          # e.g. "src/calc.py::add" or "src/calc.py:42"
    ef: int               # executed by failing tests
    ep: int               # executed by passing tests
    total_failing: int    # total failing tests in the run
    total_passing: int    # total passing tests in the run


def ochiai(s: Spectrum) -> float:
    denom = math.sqrt((s.total_failing) * (s.ef + s.ep))
    return s.ef / denom if denom > 0 else 0.0


def tarantula(s: Spectrum) -> float:
    f = (s.ef / s.total_failing) if s.total_failing else 0.0
    p = (s.ep / s.total_passing) if s.total_passing else 0.0
    return f / (f + p) if (f + p) > 0 else 0.0


def rank(spectra: list[Spectrum], metric=ochiai) -> list[tuple[str, float]]:
    """Elements ranked most→least suspicious.

    Deterministic and INPUT-ORDER-INDEPENDENT: ties break on the element name, so
    the same spectrum yields the same ranking no matter what order it arrives in.
    That invariance is what defeats the LLM's input-order bias.
    """
    scored = [(s.element, round(metric(s), 6)) for s in spectra]
    # Sort by score desc, then element name asc — a total order with no dependence
    # on input position.
    scored.sort(key=lambda t: (-t[1], t[0]))
    return scored


def build_spectra(coverage: dict[str, dict[str, bool]],
                  outcomes: dict[str, bool]) -> list[Spectrum]:
    """Turn per-test coverage + outcomes into per-element spectra.

    coverage: {test_id: {element: executed?}}
    outcomes: {test_id: passed?}
    """
    total_passing = sum(1 for p in outcomes.values() if p)
    total_failing = sum(1 for p in outcomes.values() if not p)

    elements: set[str] = set()
    for cov in coverage.values():
        elements.update(cov)

    spectra = []
    for el in elements:
        ef = ep = 0
        for test_id, passed in outcomes.items():
            if coverage.get(test_id, {}).get(el):
                if passed:
                    ep += 1
                else:
                    ef += 1
        spectra.append(Spectrum(el, ef, ep, total_failing, total_passing))
    return spectra


def format_for_prompt(ranking: list[tuple[str, float]], top: int = 8) -> str:
    """Render the ranking as prompt evidence. Only elements a failing test touched
    (score > 0) are worth showing; a zero score localises nothing."""
    rows = [(el, sc) for el, sc in ranking if sc > 0][:top]
    if not rows:
        return ""
    lines = ["<fault_localization metric=\"ochiai\">",
             "Ranked by suspiciousness (executed more by failing tests than passing):"]
    for el, sc in rows:
        lines.append(f"  {sc:.3f}  {el}")
    lines.append("</fault_localization>")
    return "\n".join(lines)
