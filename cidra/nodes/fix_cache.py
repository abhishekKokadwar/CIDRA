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
import time
from pathlib import Path
from typing import Optional

from cidra import config

log = logging.getLogger("cidra.fix_cache")

# Maximum number of entries stored before evicting oldest
MAX_CACHE_ENTRIES = 500


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
    p = Path(path or config.FIX_CACHE_PATH)
    entry = _load(p).get(fingerprint)
    if not isinstance(entry, dict):
        return None

    # Check TTL expiration if entry has expires_at
    expires_at = entry.get("expires_at")
    if expires_at is not None and time.time() > expires_at:
        log.info("Cache entry expired for %s (TTL exceeded)", fingerprint[:12])
        invalidate(fingerprint, path=p)
        return None

    return entry


def put(fingerprint: str, diff: str, category: str,
        meta: Optional[dict] = None, path: str | Path | None = None,
        ttl_seconds: Optional[float] = None) -> bool:
    """Store a verified fix. Returns True on write. Refuses an empty key/diff."""
    if not fingerprint or not diff:
        return False
    p = Path(path or config.FIX_CACHE_PATH)
    data = _load(p)

    entry_meta = dict(meta or {})
    entry_meta["updated_at"] = time.time()
    if ttl_seconds is not None:
        entry_meta["expires_at"] = time.time() + ttl_seconds

    # LRU eviction: if capacity reached, evict oldest updated entry
    if len(data) >= MAX_CACHE_ENTRIES and fingerprint not in data:
        oldest_fp = min(
            data.keys(),
            key=lambda k: data[k].get("updated_at", 0) if isinstance(data[k], dict) else 0
        )
        data.pop(oldest_fp, None)

    data[fingerprint] = {"diff": diff, "category": category, **entry_meta}
    try:
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except OSError as e:
        log.warning("fix cache not writable (%s): %s", p, e)
        return False


def invalidate(fingerprint: str, path: str | Path | None = None) -> bool:
    """Explicitly removes an entry from the cache (e.g. on code or dependency drift)."""
    if not fingerprint:
        return False
    p = Path(path or config.FIX_CACHE_PATH)
    data = _load(p)
    if fingerprint in data:
        del data[fingerprint]
        try:
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
        except OSError as e:
            log.warning("fix cache not writable during invalidate (%s): %s", p, e)
            return False
    return False
