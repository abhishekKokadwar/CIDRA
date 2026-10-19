# Real-failure corpus

Failures from real open-source projects, in the fixture format described in
[../fixtures/README.md](../fixtures/README.md). Run with:

```bash
python eval/measure.py --corpus eval/corpus --label <model> --price-in <n> --price-out <n>
```

The rules below were written before any model was run on these cases. A case is
kept or dropped by the rules alone; `EXCLUDED.json` lists every candidate that was
tried and dropped, with the reason. Do not tune CIDRA against this corpus without
saying so in the results.

## Group `bugsinpy`

Source: [BugsInPy](https://github.com/soarsmu/BugsInPy), a public set of real bugs
with the buggy commit, the fix commit and the test that exposes the bug.
Built by `python eval/build_bugsinpy.py`.

Inclusion rules, applied in this order:

1. The project imports from a source checkout without a compiled build step.
   This drops pandas, matplotlib and spaCy before anything is tried.
2. The bug's recorded Python version is one the sandbox offers (3.7 to 3.13).
3. The fix changes at most 3 non-test files and at most 30 lines in them.
4. The bug's pinned dependencies install in the sandbox (no compiler, 300 s).
   The project itself and backports of standard-library modules (`dataclasses`,
   `typing`, `enum34`, `asyncio`) are left out of the pins, because the sandbox
   puts installed packages ahead of the standard library. If the pinned set does
   not install, the same packages are tried unpinned; `meta.json` records which
   was used. Rules 5 and 6 still have to hold in that environment.
5. With the fix commit's test file added to the buggy commit, `python -m pytest`
   on that file fails with ordinary test failures (exit code 1).
6. Applying the fix's non-test changes makes the same command pass.

Selection: projects in alphabetical order, bugs in ascending number, a project
abandoned after 3 dependency-install failures in a row. Two batches, each fixed
before any model ran on its cases:

- **Batch 1** (2026-10-15, 18 cases): the first 5 bugs of each project that pass
  every rule, at most 12 tried per project. (This README said 3 and 8 until
  2026-10-19; the build script and the corpus always used 5 and 12.)
- **Batch 2** (2026-10-19): the same rules 1 to 6, continuing the same walk with
  up to 10 kept and at most 24 tried per project, counting batch 1. Its cases
  carry `"batch": 2` in `meta.json`, and results report the batches apart as
  well as together, because CIDRA was developed while batch 1 was being measured
  and batch 2 is unseen.

What each case records:

- **Failing state:** the buggy commit plus the fix commit's test file. BugsInPy
  has no CI logs, so `raw.log` is the pytest output of that state in the sandbox.
  It is shorter and cleaner than a real CI log.
- **Expected diagnosis:** set mechanically from the log. If every failure starts
  with a failed `assert` or an `AssertionError`, the case is `assertion_error`
  and a verified fix is expected. Otherwise it is `unknown` and CIDRA is expected
  to decline, because its stated scope excludes exceptions escaping application
  code. Every case has a known small fix, so "declined" still means "not fixed".
- **Reference patch:** the fix's non-test changes, in `fake_llm.json`. A `--stub`
  run replays it, which checks the fixture and the pipeline, not a model.
- **Held-out tests:** the fix commit's test file. It is the same test the log
  shows failing, so on its own it cannot catch a patch written to satisfy only
  that test. Such a case is reported as "not judged" for the false-verified rate
  until it gets tests of its own in `held_out/`, written apart from the visible
  test (other inputs, the public code path), plus a `held_out_command` in
  `meta.json` that runs them with the case's test file. A set counts once
  `measure.py --validate` shows it passes on the fix commit and fails on the
  buggy one where the visible run did not. The 5 cases CIDRA fixed (tornado-1,
  -3, -5, youtube-dl-1, -3) have such sets; `measure.py --rejudge <results>`
  judges a past run's fixes by them without calling a model.

Code excerpts in the reference patches belong to their projects and stay under
those projects' licences; each case names its repository and commits.
