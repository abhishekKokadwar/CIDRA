"""Failure fingerprinting. Phase 11 (offline slice).

Turns an isolated error region into a stable hash so an identical failure seen
again can reuse a previously verified fix instead of paying for the LLM. The
whole value depends on the hash being stable across the noise that varies run to
run — line numbers, memory addresses, temp paths, timestamps, object ids — while
staying sensitive to the actual error (exception type, message, symbol names).

Pure and deterministic: same normalized failure -> same fingerprint, always.

Scope note (docs/KNOWN_GAPS.md): this is EXACT fingerprinting. Semantic /
embedding similarity ("have we seen something *like* this") needs an embedding
model and is deferred with the egress proxy — see Phase 11 in 3_phases.md.
"""

import hashlib
import re

# Each pattern replaces run-varying noise with a fixed placeholder so two runs of
# the same failure normalize identically.
_SUBS = [
    (re.compile(r"0x[0-9a-fA-F]+"), "0xADDR"),               # memory addresses
    (re.compile(r"line \d+"), "line N"),                       # traceback line nos
    (re.compile(r":\d+:\d+"), ":N:N"),                        # file:line:col
    (re.compile(r":\d+\b"), ":N"),                            # file:line
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[ T][\d:.,]+"), "TS"),   # timestamps
    (re.compile(r"/tmp/[^\s'\"]+"), "/tmp/PATH"),            # unix temp paths
    (re.compile(r"[A-Za-z]:\\\\[^\s'\"]+|[A-Za-z]:/[^\s'\"]+"), "WINPATH"),  # win paths
    (re.compile(r"\bpytest-\d+\b"), "pytest-N"),             # pytest tmp dirs
    (re.compile(r"\b0\.\d+s\b|\b\d+\.\d+s\b"), "Ns"),        # durations
    (re.compile(r"\bat 0x[0-9a-fA-F]+"), "at 0xADDR"),       # <obj at 0x...>
    (re.compile(r"\s+"), " "),                                 # collapse whitespace
]


def normalize(error_region: str) -> str:
    """Strip run-varying noise; keep the signal (types, messages, symbols)."""
    text = error_region.strip()
    for pat, repl in _SUBS:
        text = pat.sub(repl, text)
    return text.strip()


def fingerprint(error_region: str) -> str:
    """Stable SHA256 of the normalized failure. Empty input -> empty string."""
    if not error_region or not error_region.strip():
        return ""
    return hashlib.sha256(normalize(error_region).encode()).hexdigest()
