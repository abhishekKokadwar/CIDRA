# Contributing to CIDRA

CIDRA is created and maintained by Abhishek Kokadwar ([@abhishekKokadwar](https://github.com/abhishekKokadwar)).
This file says how changes are made, so the history stays readable and every change can be traced to who made it and why.

## Workflow

1. **Branch from `main`.** Never commit to `main` directly.

   | Prefix | For | Example |
   |---|---|---|
   | `feat/` | A new capability | `feat/install-command-ladder` |
   | `fix/` | A bug fix | `fix/revert-previous-patch` |
   | `docs/` | Documentation only | `docs/known-gaps-review` |
   | `test/` | Tests or evaluation only | `test/bugsinpy-second-model` |
   | `chore/` | Build, release, dependencies, CI | `chore/release-0-3-0` |

2. **Keep the branch short-lived.** Before opening a pull request, rebase it on the latest `main`
   (`git fetch origin && git rebase origin/main`). The telemetry bot commits to `main`, so expect to rebase.
3. **Open a pull request** against `main`. Its description says what changed, why, and how it was checked.
4. **CI must be green** before merging: branch protection requires the `ci-ok` check of
   [test-cidra.yml](.github/workflows/test-cidra.yml). CI is tiered by the files a PR changes:

   | PR changes | Runs |
   |---|---|
   | only docs (`*.md`, `docs/`, `eval/results/`) | nothing but the `ci-ok` gate |
   | anything else, including `docs/requirements.yml` | unit and server tests; integration tests, adversarial and security suites in the real sandbox; the full pipeline on the 7 practice fixtures with the stub model; the dashboard's lint, component tests and build; browser tests of the dashboard against the real server; the built package installed and run; a dependency audit and CodeQL; then the requirements check |

   The requirements check fails unless every requirement in [docs/requirements.yml](docs/requirements.yml)
   has a test tagged `@pytest.mark.req("<id>")` (or, in the dashboard, a test whose title starts with `[<id>]`)
   that ran and passed (skipped does not count), and every
   CI job it names passed. A new requirement or roadmap item goes in that file with the tests that prove it.
   A push to `main` runs every tier, and so does a nightly run on `main`, which installs the newest
   versions of the unpinned dependencies; a failed nightly opens an issue. Once a week
   `real-model.yml` runs three practice fixtures with the real model (about $0.02, capped); the
   paid BugsInPy run is never in CI.
   Third-party Actions are pinned to a commit (a test fails otherwise); Dependabot proposes their
   updates, and the pip and npm ones, weekly, and each update PR runs the full CI.
   Coverage has floors: the unit, server and integration runs together must cover `cidra/` at least
   as much as `fail_under` in `pyproject.toml`, and the dashboard's component tests at least the
   thresholds in `dashboard/vite.config.js`. Raise a floor when coverage rises; never lower one to
   get a change through.
5. **Merge with "Rebase and merge"**, so each commit lands on `main` as written and keeps its author.
   Use "Squash and merge" only for a branch whose commits are work-in-progress noise.
6. Delete the branch after merging.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <summary in the imperative, lower case, no full stop>

<body: what was wrong or missing, and why this change. Wrap at about 72 characters.>
```

**Types:** `feat` (new capability), `fix` (bug fix), `docs`, `test`, `refactor` (no behaviour change),
`ci`, `chore` (build, release, dependencies). Add `!` after the scope for a breaking change
(`feat(action)!: …`) and explain it in the body.

**Scopes** name the part of the code that changed. Use one of these:

| Scope | Code |
|---|---|
| `action` | `action.yml` |
| `cli` | `cidra/cli.py` |
| `llm` | `cidra/integrations/llm.py` |
| `sandbox` | `cidra/sandbox/` |
| `audit` | `cidra/nodes/audit.py` |
| `fix`, `checkout`, `publish`, `state` | the matching node or module |
| `server` | `cidra/server/` |
| `dashboard` | `dashboard/` |
| `security` | changes made for a threat-model requirement |
| `eval` | `eval/` |
| `readme` | `README.md` (with `docs`) |

**Rules:**

- One logical change per commit. A bug fix and the test that proves it go in the same commit.
- The body explains *why*. The diff already shows *what*.
- Commits are authored under your own name and email (`git config user.name` / `user.email`).
  No generated attribution lines (`Co-Authored-By` for tools, "Generated with …").
- Never rewrite `main`'s history. Force-push only your own feature branch.

Examples from this repository:

```
fix(state): declare pr_branch so the existing-PR path is reachable
feat(action): install_command and test_command inputs
docs: correct README and known gaps against the code
```

## Before you push

```bash
ruff check .                  # errors and likely bugs (rules in pyproject.toml); CI fails on any
mypy                          # type checks on cidra/; CI fails on any
pytest -q                     # unit and server suites, no Docker or key needed
git status                    # the test suite rewrites some tracked files; do not commit them
```

The dashboard (`dashboard/`):

```bash
npm ci && npm run lint && npm test
npm run build                 # also refreshes cidra/static; commit it with any change to dashboard/src
npx playwright install chromium && npm run e2e   # browser tests against the real server, on scratch data
```

CI runs the Docker tiers for you. To run them locally (Docker up):

```bash
pytest -q tests/integration
python eval/adversarial/run_adversarial.py
python eval/security_fixtures/run_benchmark.py --tier 2
CIDRA_PRACTICE_REPO=/path/to/cidra-practice python eval/measure.py --stub --check
```

A change meant to improve repair results should also be measured with the real model on the
BugsInPy corpus (`eval/measure.py --corpus eval/corpus`), and the result file committed under `eval/results/`.

Open gaps and their status are in [docs/KNOWN_GAPS.md](docs/KNOWN_GAPS.md).
