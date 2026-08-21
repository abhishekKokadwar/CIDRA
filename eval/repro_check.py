"""Phase 4 exit criterion: every fixture must reproduce RED in the sandbox."""
import json, pathlib, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from cidra.sandbox.runner import Session

PRACTICE = pathlib.Path("d:/CODES/cidra-practice")
FIXTURES = pathlib.Path(__file__).parent / "fixtures"
# F-03 breaks by REMOVING the env var from CI, so the sandbox must omit it too.
ENV = {"F-03": "", "default": "API_TOKEN=tok_practice_value "}

fails = 0
for d in sorted(p for p in FIXTURES.iterdir() if p.is_dir()):
    meta = json.loads((d / "meta.json").read_text())
    subprocess.run(["git", "-C", str(PRACTICE), "checkout", "-q", meta["branch"]], check=True)
    prefix = ENV.get(d.name, ENV["default"])
    with Session(PRACTICE) as s:
        s.install("pip install --quiet -r requirements.txt")
        r = s.run("test", f"{prefix}python -m pytest -q 2>&1")
    red = not r.passed
    tail = r.stdout_tail.strip().splitlines()[-1][:60] if r.stdout_tail.strip() else ""
    print(f"{'ok  ' if red else 'FAIL'} {d.name:<7} exit={r.exit_code} {tail}")
    fails += not red

subprocess.run(["git", "-C", str(PRACTICE), "checkout", "-q", "main"], check=True)
print(f"\n{len(list(FIXTURES.iterdir())) - fails}/{len(list(FIXTURES.iterdir()))} reproduce red")
sys.exit(1 if fails else 0)
