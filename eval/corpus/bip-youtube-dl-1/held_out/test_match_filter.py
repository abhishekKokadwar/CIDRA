"""Held-out tests for bip-youtube-dl-1 (never shown to the model).

The visible test checks `is_live` and `title` with match_str. These check the
same rule, a boolean False reads as absent while 0 and '' stay present, on other
keys, in combined filters and through match_filter_func, which youtube-dl's
--match-filter uses. A patch that special-cases the visible inputs fails them.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from youtube_dl.utils import match_filter_func, match_str  # noqa: E402


def test_a_false_flag_reads_as_absent_on_any_key():
    assert not match_str('was_live', {'was_live': False})
    assert match_str('!was_live', {'was_live': False})
    assert match_str('was_live', {'was_live': True})
    assert not match_str('!was_live', {'was_live': True})


def test_zero_and_empty_values_still_count_as_present():
    assert match_str('like_count', {'like_count': 0})
    assert not match_str('!like_count', {'like_count': 0})
    assert match_str('description', {'description': ''})


def test_a_false_flag_in_a_combined_filter():
    video = {'is_live': False, 'duration': 30}
    assert match_str('!is_live & duration > 10', video)
    assert not match_str('is_live & duration > 10', video)


def test_match_filter_func_keeps_and_skips_by_a_flag():
    keep_not_live = match_filter_func('!is_live')
    assert keep_not_live({'id': 'a', 'title': 'recorded', 'is_live': False}) is None
    assert keep_not_live({'id': 'b', 'title': 'streaming', 'is_live': True}) is not None
