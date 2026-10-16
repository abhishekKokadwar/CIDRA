"""Is the code a fix must change in the model's view? Free: no model, no sandbox.

For each fixable corpus case, build the fix prompt's file context exactly as the
pipeline does, on the failing commit, and check that the lines the reference fix
changes appear in it. A model cannot edit code it was never shown, so this is an
upper bound on what any model can fix with that context.

    python eval/context_visibility.py              # the BugsInPy corpus
    python eval/context_visibility.py bip-tornado-5
"""

import io
import json
import pathlib
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cidra.nodes.fix import _context  # noqa: E402
from cidra.nodes.ingest import isolate_error  # noqa: E402
from cidra.state import Analysis  # noqa: E402
from eval.corpus_repo import corpus_clone, resolve, with_files_from  # noqa: E402
from scripts.fake_llm import diff_to_edits  # noqa: E402

CORPUS = ROOT / "eval" / "corpus"


def changed_lines(edit: dict) -> list[str]:
    """The lines a reference edit removes, or for a pure addition its context."""
    old, new = edit["old"].splitlines(), set(edit["new"].splitlines())
    return [l for l in old if l not in new and l.strip()] or [l for l in old if l.strip()]


def check(case: pathlib.Path) -> tuple[bool, int]:
    meta = json.loads((case / "meta.json").read_text(encoding="utf-8"))
    answers = json.loads((case / "fake_llm.json").read_text(encoding="utf-8"))
    repo = corpus_clone(meta["repo_url"])
    ref = resolve(repo, meta["failing_ref"])
    if meta.get("failing_tests_from_fix"):
        ref = with_files_from(repo, ref, resolve(repo, meta["fix_ref"]), meta["failing_tests_from_fix"])
    log = (case / "raw.log").read_text(encoding="utf-8", errors="replace")
    with tempfile.TemporaryDirectory() as tmp:
        tarfile.open(fileobj=io.BytesIO(subprocess.check_output(["git", "-C", repo, "archive", ref]))).extractall(tmp)
        context = _context({"run_id": "visibility", "source_dir": tmp,
                            "error_region": isolate_error({"raw_log": log})["error_region"],
                            "analysis": Analysis(**answers["Analysis"])})
    edits = [e for e in diff_to_edits(answers["Patch"]["diff"]) if e["path"].endswith(".py")]
    return all(line in context for e in edits for line in changed_lines(e)), len(context)


def main() -> int:
    cases = [CORPUS / c for c in sys.argv[1:]] or sorted(p for p in CORPUS.iterdir() if (p / "meta.json").exists())
    fixable = [c for c in cases
               if json.loads((c / "expected.json").read_text())["expected_outcome"] == "verified_fix"]
    seen = 0
    for case in fixable:
        visible, size = check(case)
        seen += visible
        print(f"{case.name:<18} {'visible' if visible else 'NOT visible':<12} context {size:>6} chars")
    print(f"\nfix location in view: {seen}/{len(fixable)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
