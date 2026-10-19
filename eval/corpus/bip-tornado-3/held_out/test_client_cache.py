"""Held-out tests for bip-tornado-3 (never shown to the model).

The visible test runs a subprocess whose shutdown closes an HTTPClient after its
cache entry is gone. These check the same rule in-process: closing a client
whose cache entry has already disappeared is not an error, a closed client
leaves the cache, and a genuinely mixed-up cache is still reported.
"""
from tornado.httpclient import AsyncHTTPClient
from tornado.testing import AsyncTestCase


class HeldOutClientCacheTest(AsyncTestCase):
    def test_closing_after_the_cache_entry_is_gone(self):
        client = AsyncHTTPClient()
        client._instance_cache.pop(self.io_loop)  # as when the weak reference is cleared first
        client.close()  # must not raise

    def test_a_closed_client_leaves_the_cache(self):
        client = AsyncHTTPClient()
        client.close()
        fresh = AsyncHTTPClient()
        self.assertIsNot(fresh, client)
        fresh.close()

    def test_a_different_client_in_the_cache_is_still_reported(self):
        client = AsyncHTTPClient()
        other = AsyncHTTPClient(force_instance=True)
        client._instance_cache[self.io_loop] = other
        with self.assertRaises(RuntimeError):
            client.close()
        other.close()
