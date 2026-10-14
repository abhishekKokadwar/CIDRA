"""Git plumbing shared by the measurement harness and the corpus builders.

A corpus fixture names a repository and two commits. These helpers put the
repository on disk once and make sure the commits a run needs are in it.
"""

import os
import pathlib
import re
import subprocess
import tempfile


def git(repo: str, *args: str, env: dict | None = None) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True,
                                   stderr=subprocess.DEVNULL, env=env).strip()


def corpus_clone(url: str) -> str:
    """A local clone of a fixture's repository, made once and reused."""
    from cidra import config
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", url.split("://")[-1].rstrip("/").removesuffix(".git")).strip("_")
    dest = pathlib.Path(config.WORKTREE_ROOT).resolve() / "corpus" / name
    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.check_call(["git", "clone", "--quiet", url, str(dest)])
    return str(dest)


def pin(repo: str, sha: str) -> str:
    """Tag a commit. The pipeline clones this clone, and a commit that no branch
    or tag reaches (a pull request head, a commit built here) would not come along."""
    git(repo, "tag", "--force", f"cidra-pin-{sha[:12]}", sha)
    return sha


def resolve(repo: str, ref: str) -> str:
    """The commit `ref` names, fetching it if the clone does not have it yet."""
    try:
        return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    except subprocess.CalledProcessError:
        git(repo, "fetch", "--quiet", "origin", ref)
        return git(repo, "rev-parse", "--verify", "FETCH_HEAD^{commit}")


def with_files_from(repo: str, base: str, source: str, paths: list[str]) -> str:
    """A commit that is `base` with `paths` taken from `source`.

    Bug datasets give a buggy commit and a fix commit whose new test exposes the
    bug. The failing state a CI run would have seen is the buggy code with that
    test. Same inputs give the same commit id.
    """
    with tempfile.TemporaryDirectory() as tmp:
        stamp = "2000-01-01T00:00:00+0000"
        env = {**os.environ, "GIT_INDEX_FILE": str(pathlib.Path(tmp) / "index"),
               "GIT_AUTHOR_NAME": "cidra-corpus", "GIT_AUTHOR_EMAIL": "corpus@cidra.invalid",
               "GIT_COMMITTER_NAME": "cidra-corpus", "GIT_COMMITTER_EMAIL": "corpus@cidra.invalid",
               "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
        git(repo, "read-tree", base, env=env)
        for path in paths:
            entry = git(repo, "ls-tree", source, "--", path)
            if not entry:
                raise ValueError(f"{path} does not exist at {source[:12]}")
            mode, kind, blob = entry.split("\t")[0].split()
            if kind != "blob":
                raise ValueError(f"{path} is not a file")
            git(repo, "update-index", "--add", "--cacheinfo", f"{mode},{blob},{path}", env=env)
        tree = git(repo, "write-tree", env=env)
        return git(repo, "commit-tree", tree, "-p", base, "-m",
                   f"corpus: {base[:12]} with tests from {source[:12]}", env=env)
