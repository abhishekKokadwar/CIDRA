# Test suite

Grouped by what a test needs to run.

```
tests/
├── unit/          pure, fast, no Docker — logic, parsers, routers, git wrapper
├── server/        Phase 7 webhook — FastAPI TestClient, mocked graph/GitHub
└── integration/   needs a running Docker daemon — sandbox + full pipeline
```

## Running

```bash
pytest -m "not docker"     # everything except the Docker integration tests (fast, offline)
pytest                     # full suite (needs Docker + the cidra-sandbox:base image)
pytest tests/unit          # just one group
```

`conftest.py` (repo root) puts the repo on `sys.path` and anchors the working
directory to the root, so fixture paths like `eval/fixtures/...` resolve no matter
where pytest is invoked. Integration tests are auto-marked `docker` by
`tests/integration/conftest.py`.

## Separate eval harnesses (not part of pytest)

- `eval/run_eval.py` — fixture-corpus accuracy (Tier 1/2)
- `eval/repro_check.py` — every fixture reproduces red in the sandbox
- `eval/adversarial/run_adversarial.py` — ADV-01..08 sandbox containment
- `eval/security_fixtures/run_benchmark.py` — SEC-01..08 security benchmark
- `eval/sbfl_bias_eval.py` — SBFL localization is input-order-independent
