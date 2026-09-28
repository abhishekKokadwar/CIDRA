"""Fault-localization node: collect a coverage spectrum, rank with SBFL. Phase 8.

Runs after reproduction, before the fix path, using the live sandbox session.
Collects per-test coverage inside the container, builds the spectrum, and ranks
elements by suspiciousness (sbfl.py). The ranking is stashed on state as prompt
evidence for a re-analysis (see analyze) so the model reasons from a mathematical
order rather than input position.

Best-effort by design (docs/3_phases.md §8): coverage.py + pytest must be present
in the session, which they are only if the repo installed them. If they are
absent, this degrades to "no SBFL evidence" and the pipeline is exactly as it was
before Phase 8 — never a failure. The SBFL math and its input-order invariance
are what the phase proves; live collection is an enhancement on top.
"""

import json
import logging

from cidra.nodes.environment import session_for
from cidra.nodes.sbfl import build_spectra, rank, format_for_prompt
from cidra.state import DebugState

log = logging.getLogger("cidra.localize")

# A tiny pytest plugin, written into the container, that records which source
# lines each test executes and the test's outcome — emitted as one JSON blob.
# CIDRA-authored and fixed; never assembled from model output.
_COLLECT = r'''
import json, coverage, pytest

_spec = {}   # nodeid -> {element: True}
_out = {}    # nodeid -> passed?

class _P:
    def __init__(self):
        self.cov = coverage.Coverage(branch=False)
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self, item):
        self.cov.start()
        yield
        self.cov.stop()
        data = self.cov.get_data()
        touched = {}
        for f in data.measured_files():
            if "/site-packages/" in f or f.endswith("conftest.py"):
                continue
            for ln in data.lines(f) or []:
                touched[f"{f}:{ln}"] = True
        _spec[item.nodeid] = touched
        self.cov.erase()
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        rep = (yield).get_result()
        if rep.when == "call":
            _out[item.nodeid] = rep.passed

def pytest_unconfigure(config):
    print("CIDRA_SBFL_JSON=" + json.dumps({"cov": _spec, "out": _out}))

def pytest_configure(config):
    config.pluginmanager.register(_P())
'''


def _parse_blob(stdout: str) -> dict | None:
    for line in stdout.splitlines():
        if line.startswith("CIDRA_SBFL_JSON="):
            try:
                return json.loads(line[len("CIDRA_SBFL_JSON="):])
            except json.JSONDecodeError:
                return None
    return None


def localize(state: DebugState) -> dict:
    """Collect coverage + rank suspiciousness. Best-effort; empty on any miss."""
    session = session_for(state["run_id"])
    if session is None:
        return {}
    # Probe: are the tools even here? Cheap check, avoids a pointless full run.
    probe = session.run("test", "python -c \"import coverage, pytest\" 2>&1")
    if not probe.passed:
        log.info("SBFL skipped: coverage/pytest absent in session")
        return {}

    # Write the plugin and run the suite once under it (network is already off).
    session.run("test", "cat > /work/_cidra_sbfl.py <<'PYEOF'\n" + _COLLECT + "\nPYEOF")
    run = session.run("test", "python -m pytest -q -p no:cacheprovider "
                      "-p _cidra_sbfl 2>&1", timeout_s=300)
    blob = _parse_blob(run.stdout_tail)
    if not blob or not blob.get("out"):
        log.info("SBFL: no spectrum collected")
        return {}

    spectra = build_spectra(blob["cov"], blob["out"])
    ranking = rank(spectra)
    evidence = format_for_prompt(ranking)
    top = [el for el, _ in ranking[:5]]
    return {"sbfl_ranking": top, "sbfl_evidence": evidence}
