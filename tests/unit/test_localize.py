"""Phase 8.3 — localize node (best-effort) + SBFL evidence reaches the fix prompt."""

from cidra.nodes import localize


def test_localize_no_session_is_noop():
    # No sandbox session (unit path): degrade cleanly, never raise.
    assert localize.localize({"run_id": "nope"}) == {}


def test_parse_blob_extracts_json():
    stdout = ("some pytest noise\n"
              'CIDRA_SBFL_JSON={"cov": {"t1": {"a:1": true}}, "out": {"t1": false}}\n'
              "more noise\n")
    blob = localize._parse_blob(stdout)
    assert blob["out"] == {"t1": False}
    assert blob["cov"]["t1"] == {"a:1": True}


def test_parse_blob_missing_returns_none():
    assert localize._parse_blob("no marker here") is None
    assert localize._parse_blob("CIDRA_SBFL_JSON=not json") is None


def test_sbfl_evidence_is_injected_into_fix_context(monkeypatch):
    """The ranking must actually reach the model's context (that's the point)."""
    from cidra.nodes import fix
    from cidra.nodes import environment
    monkeypatch.setattr(environment, "session_for", lambda rid: None)
    monkeypatch.setattr(fix, "session_for", lambda rid: None, raising=False)
    ctx = fix._context({
        "run_id": "r", "error_region": "boom",
        "sbfl_evidence": "<fault_localization>SUSPECT src/calc.py::add</fault_localization>",
        "analysis": None,
    })
    assert "fault_localization" in ctx and "src/calc.py::add" in ctx


def test_no_evidence_means_no_block(monkeypatch):
    from cidra.nodes import fix, environment
    monkeypatch.setattr(environment, "session_for", lambda rid: None)
    ctx = fix._context({"run_id": "r", "error_region": "boom", "analysis": None})
    assert "fault_localization" not in ctx
