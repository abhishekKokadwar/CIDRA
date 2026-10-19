"""Held-out tests for bip-tornado-1 (never shown to the model).

The visible test calls set_nodelay(True) in open() and only checks that a
message still arrives. These check that the option really reaches the live
socket, also when set later (in on_message) and switched off again, and that
the connection still closes normally afterwards.
"""
import socket

from tornado.concurrent import Future
from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.web import Application
from tornado.websocket import WebSocketHandler, websocket_connect


def _nodelay(handler):
    sock = handler.ws_connection.stream.socket
    return int(bool(sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)))


class SetInOpen(WebSocketHandler):
    def initialize(self, closed):
        self.closed = closed

    def open(self):
        self.set_nodelay(True)
        on = _nodelay(self)
        self.set_nodelay(False)
        self.write_message("on=%d off=%d" % (on, _nodelay(self)))

    def on_close(self):
        self.closed.set_result(self.close_code)


class SetInOnMessage(WebSocketHandler):
    def on_message(self, message):
        self.set_nodelay(True)
        self.write_message("nodelay=%d" % _nodelay(self))


class HeldOutNoDelayTest(AsyncHTTPTestCase):
    def get_app(self):
        self.closed = Future()
        return Application([("/open", SetInOpen, dict(closed=self.closed)), ("/message", SetInOnMessage)])

    def _url(self, path):
        return "ws://127.0.0.1:%d%s" % (self.get_http_port(), path)

    @gen_test
    def test_set_and_cleared_in_open_on_the_live_socket(self):
        ws = yield websocket_connect(self._url("/open"))
        self.assertEqual((yield ws.read_message()), "on=1 off=0")
        ws.close(code=1001)
        self.assertEqual((yield self.closed), 1001)

    @gen_test
    def test_set_after_open_in_on_message(self):
        ws = yield websocket_connect(self._url("/message"))
        ws.write_message("hi")
        self.assertEqual((yield ws.read_message()), "nodelay=1")
        ws.close()
