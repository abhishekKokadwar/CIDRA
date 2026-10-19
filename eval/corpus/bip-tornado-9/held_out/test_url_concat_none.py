"""Held-out tests for bip-tornado-9 (never shown to the model).

The visible test checks that url_concat(url, None) returns a plain URL as it
is. These check the same rule on URLs whose query a parse-and-rebuild would
change (an encoded space, a value-less key, a fragment), and on a URL with no
query at all.
"""
import unittest

from tornado.httputil import url_concat


class HeldOutUrlConcatNoneTest(unittest.TestCase):
    def test_none_leaves_an_encoded_query_untouched(self):
        url = "https://example.com/p?q=a%20b&flag#top"
        self.assertEqual(url_concat(url, None), url)

    def test_none_on_a_url_without_a_query(self):
        self.assertEqual(url_concat("http://example.com/foo", None), "http://example.com/foo")
