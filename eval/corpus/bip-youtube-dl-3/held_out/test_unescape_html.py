"""Held-out tests for bip-youtube-dl-3 (never shown to the model).

The visible test checks one string, '&a&quot;'. These check the same rule (a
stray '&' must not swallow the entity after it) on other strings, and that
well-formed and unknown entities behave as before. A patch that special-cases
the visible string fails them.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from youtube_dl.utils import unescapeHTML  # noqa: E402


def test_an_ampersand_without_a_semicolon_before_a_real_entity():
    assert unescapeHTML('Tom &amp Jerry &amp; co') == 'Tom &amp Jerry & co'


def test_numeric_entities_after_a_stray_ampersand():
    assert unescapeHTML('x &y &#39;z&#x2F;') == "x &y 'z/"


def test_well_formed_entities_still_decode():
    assert unescapeHTML('&lt;b&gt; &quot;q&quot; &eacute;') == '<b> "q" é'


def test_unknown_entities_stay_literal():
    assert unescapeHTML('&foo; &#xZZ;') == '&foo; &#xZZ;'
