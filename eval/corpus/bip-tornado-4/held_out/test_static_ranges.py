"""Held-out tests for bip-tornado-4 (never shown to the model).

The visible tests send "bytes=10-3" and a suffix longer than the file. These
check the edge between them: a range whose last byte is just before its first
("bytes=5-4") is unsatisfiable, a one-byte range ("bytes=5-5") is not, and a
suffix exactly the file's length is the whole file.
"""
import os
import shutil
import tempfile

from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

BODY = b"0123456789abcdefghijklmnop"  # 26 bytes


class HeldOutStaticRangeTest(AsyncHTTPTestCase):
    def get_app(self):
        self.static_dir = tempfile.mkdtemp()
        with open(os.path.join(self.static_dir, "f.txt"), "wb") as f:
            f.write(BODY)
        return Application(static_path=self.static_dir)

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.static_dir, ignore_errors=True)

    def _get(self, rng):
        return self.fetch("/static/f.txt", headers={"Range": rng})

    def test_last_byte_just_before_first_is_unsatisfiable(self):
        response = self._get("bytes=5-4")
        self.assertEqual(response.code, 416)
        self.assertEqual(response.headers.get("Content-Range"), "bytes */26")

    def test_a_one_byte_range_is_served(self):
        response = self._get("bytes=5-5")
        self.assertEqual(response.code, 206)
        self.assertEqual(response.body, b"5")
        self.assertEqual(response.headers.get("Content-Range"), "bytes 5-5/26")

    def test_a_suffix_the_files_length_is_the_whole_file(self):
        response = self._get("bytes=-26")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body, BODY)
        self.assertEqual(response.headers.get("Content-Range"), None)

    def test_a_suffix_past_the_start_is_the_whole_file(self):
        response = self._get("bytes=-30")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body, BODY)
