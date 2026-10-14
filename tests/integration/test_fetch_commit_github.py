"""Webhook mode against real GitHub: fetch one commit of this public repository.

Needs network access to github.com (CI has it). No token: the repository is public.
"""

from pathlib import Path

from cidra import config
from cidra.nodes import environment, publish

# "feat(eval): measure any repository from its fixture alone", on main.
COMMIT = "b02bfc4189a28493f58f0723b2c3989da89660c6"


def test_fetches_a_commit_from_github(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKTREE_ROOT", str(tmp_path / "wt"))
    monkeypatch.setattr(config, "GITHUB_API", "https://api.github.com")
    monkeypatch.setattr(config, "GITHUB_TOKEN_RO", "")
    out = environment.checkout_commit({"run_id": "gh1", "repo": "abhishekKokadwar/CIDRA", "commit_sha": COMMIT})
    tree = Path(out["source_dir"])
    assert (tree / "eval" / "measure.py").is_file(), out.get("analysis_error")
    assert not (tree / "eval" / "corpus").exists()  # added after this commit
    assert not (tree / ".git").exists()
    publish.cleanup({"run_id": "gh1"})
    assert not tree.exists() and not Path(out["repo_dir"]).exists()
