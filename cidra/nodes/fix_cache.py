"""Verified-fix cache keyed by failure fingerprint. Phase 11 (offline slice).

When a fix is verified green, we store {fingerprint -> {diff, category, ...}}.
On a later run whose failure fingerprints identically, we can skip the LLM
(analyze + generate_fix) and reuse the diff. That is the token-cost win and the
"<1s, no LLM" path in docs/3_phases.md §11.

A JSON file, not a DB: the cache is small, human-inspectable, and needs no
dependency. Reads/writes are whole-file and best-effort — a corrupt or missing
cache degrades to "no hit", never an error, so the pipeline is exactly as it was
without a cache.

Only VERIFIED fixes are ever written (the caller enforces this): caching an
unverified diff would reintroduce the false-`verified` risk the whole design
avoids.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from cidra import config

log = logging.getLogger("cidra.fix_cache")


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    except OSError as e:  # unreadable cache is a miss, not a crash
        log.warning("fix cache unreadable (%s): %s", path, e)
        return {}


def get(fingerprint: str, path: str | Path | None = None) -> Optional[dict]:
    """The cached entry for a fingerprint, or None. Empty fingerprint never hits."""
    if not fingerprint:
        return None
    entry = _load(Path(path or config.FIX_CACHE_PATH)).get(fingerprint)
    return entry if isinstance(entry, dict) else None


def put(fingerprint: str, diff: str, category: str,
        meta: Optional[dict] = None, path: str | Path | None = None) -> bool:
    """Store a verified fix. Returns True on write. Refuses an empty key/diff."""
    if not fingerprint or not diff:
        return False
    p = Path(path or config.FIX_CACHE_PATH)
    data = _load(p)
    data[fingerprint] = {"diff": diff, "category": category, **(meta or {})}
    try:
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except OSError as e:
        log.warning("fix cache not writable (%s): %s", p, e)
        return False
