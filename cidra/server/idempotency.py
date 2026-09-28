"""Idempotency store. Phase 7, step 7.2.

GitHub retries a webhook delivery on any non-2xx or timeout, and can deliver the
same event more than once regardless. Without a dedupe key CIDRA would spawn a
second container and post a second comment for one failure.

The key is (run_id, commit_sha): a given CI run at a given commit is processed
at most once. `claim()` is the atomic gate — the UNIQUE constraint means exactly
one caller wins the INSERT; every retry sees IntegrityError and is told "already
claimed". SQLite so it survives a process restart (an in-memory set would forget
across the very restart a retry is most likely to follow).

Redis would only be needed if multiple CIDRA processes shared one store; a single
webhook process does not, so SQLite is the right scope here (docs/3_phases.md §7).
"""

import sqlite3
import time
from pathlib import Path

DEFAULT_PATH = Path("cidra_idempotency.db")


class IdempotencyStore:
    def __init__(self, path: str | Path = DEFAULT_PATH):
        # check_same_thread=False: FastAPI BackgroundTasks may touch it off-thread.
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS seen ("
            "  run_id TEXT NOT NULL,"
            "  commit_sha TEXT NOT NULL,"
            "  claimed_at REAL NOT NULL,"
            "  PRIMARY KEY (run_id, commit_sha)"
            ")"
        )
        self._db.commit()

    def claim(self, run_id: str, commit_sha: str) -> bool:
        """True if this (run_id, commit_sha) is newly claimed; False if seen.

        Atomic: the PRIMARY KEY makes a duplicate INSERT raise, so only the first
        caller for a key gets True. A duplicate delivery gets False and is dropped.
        """
        try:
            self._db.execute(
                "INSERT INTO seen (run_id, commit_sha, claimed_at) VALUES (?, ?, ?)",
                (str(run_id), str(commit_sha), time.time()),
            )
            self._db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def close(self) -> None:
        self._db.close()
