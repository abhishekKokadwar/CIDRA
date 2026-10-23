"""Held-out tests for bip-tornado-8 (never shown to the model).

The visible test leaves out Sec-WebSocket-Key and expects a 400. These send it
empty, which is just as invalid, and check that the server still accepts a
proper WebSocket connection after turning a bad one away.
"""
from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.web import Application
from tornado.websocket import WebSocketHandler, websocket_connect

UPGRADE = {"Connection": "Upgrade", "Upgrade": "WebSocket", "Sec-WebSocket-Version": "13"}


class Echo(WebSocketHandler):
    def on_message(self, message):
        self.write_message(message)


class HeldOutHeaderTest(AsyncHTTPTestCase):
    def get_app(self):
        return Application([("/ws", Echo)])

    def test_an_empty_key_is_a_bad_request(self):
        response = self.fetch("/ws", headers=dict(UPGRADE, **{"Sec-WebSocket-Key": ""}))
        self.assertEqual(response.code, 400)

    @gen_test
    def test_a_good_connection_works_after_a_bad_one(self):
        response = yield self.http_client.fetch(self.get_url("/ws"), headers=UPGRADE, raise_error=False)
        self.assertEqual(response.code, 400)
        ws = yield websocket_connect("ws://127.0.0.1:%d/ws" % self.get_http_port())
        ws.write_message("hi")
        self.assertEqual((yield ws.read_message()), "hi")
        ws.close()
