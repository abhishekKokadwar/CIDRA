"""Held-out tests for bip-tornado-6 (never shown to the model).

The visible test counts the asyncio-to-IOLoop map after ten loops. These check
the same rule directly: one closed IOLoop leaves the map at once, and many loops
closed through asyncio's own interface are swept when the next loop starts.
"""
import asyncio
import unittest

from tornado.ioloop import IOLoop
from tornado.platform.asyncio import AsyncIOLoop


class HeldOutAsyncioMapTest(unittest.TestCase):
    def setUp(self):
        AsyncIOLoop().close()
        self.orig_policy = asyncio.get_event_loop_policy()
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

    def tearDown(self):
        asyncio.get_event_loop().close()
        asyncio.set_event_loop_policy(self.orig_policy)

    def test_a_closed_ioloop_leaves_the_map(self):
        loop = AsyncIOLoop()
        inner = loop.asyncio_loop
        self.assertIn(inner, IOLoop._ioloop_for_asyncio)
        loop.close()
        self.assertNotIn(inner, IOLoop._ioloop_for_asyncio)

    def test_loops_closed_through_asyncio_are_swept_by_the_next_loop(self):
        before = len(IOLoop._ioloop_for_asyncio)
        for _ in range(25):
            loop = asyncio.new_event_loop()
            loop.call_soon(IOLoop.current)
            loop.call_soon(loop.stop)
            loop.run_forever()
            loop.close()
        AsyncIOLoop().close()
        self.assertLessEqual(len(IOLoop._ioloop_for_asyncio), before)
