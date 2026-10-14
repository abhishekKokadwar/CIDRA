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
4. **CI must be green** (`test-cidra.yml`) before merging.
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
pytest -q                     # unit and server suites, no Docker or key needed
git status                    # the test suite rewrites some tracked files; do not commit them
```

Changes to `cidra/sandbox/`, `cidra/git_ops.py` or `cidra/nodes/checkout.py` also need the Docker
integration tests (`CIDRA_PRACTICE_REPO=... pytest tests/integration`) and the adversarial suite
(`python eval/adversarial/run_adversarial.py`). A change that affects repair results should be measured
with `eval/measure.py`, and the result file committed under `eval/results/`.

Open gaps and their status are in [docs/KNOWN_GAPS.md](docs/KNOWN_GAPS.md).
