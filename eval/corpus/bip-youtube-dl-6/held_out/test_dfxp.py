"""Held-out tests for bip-youtube-dl-6 (never shown to the model).

The visible test checks lines with invalid timestamps. These check lines with a
missing timestamp attribute: a line without `begin`, or with neither `end` nor
`dur`, is skipped, and the lines around it are kept.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from youtube_dl.utils import dfxp2srt  # noqa: E402

DFXP = '''<?xml version="1.0" encoding="UTF-8"?>
<tt xmlns="http://www.w3.org/ns/ttml" xml:lang="en">
<body><div xml:lang="en">
<p begin="0" end="1">First</p>
<p end="3">No begin</p>
<p begin="4">No end or dur</p>
<p begin="2" dur="1">Last</p>
</div></body>
</tt>'''


def test_lines_missing_a_timestamp_are_skipped():
    srt = dfxp2srt(DFXP)
    assert 'First' in srt and 'Last' in srt
    assert 'No begin' not in srt and 'No end or dur' not in srt
