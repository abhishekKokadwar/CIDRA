"""Held-out tests for bip-youtube-dl-10 (never shown to the model).

The visible test checks one double-quoted string with \\n and \\u escapes. These
check the same escapes in object values, in single-quoted strings and inside
arrays, through json.loads of the result.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from youtube_dl.utils import js_to_json  # noqa: E402


def test_a_newline_escape_in_an_object_value():
    assert json.loads(js_to_json('{a: "line1\\nline2", b: 3}')) == {'a': 'line1\nline2', 'b': 3}


def test_a_unicode_escape_in_a_single_quoted_string():
    assert json.loads(js_to_json("{b: 'it\\u0027s'}")) == {'b': "it's"}


def test_escapes_inside_an_array():
    assert json.loads(js_to_json('["p\\n", "q"]')) == ['p\n', 'q']
