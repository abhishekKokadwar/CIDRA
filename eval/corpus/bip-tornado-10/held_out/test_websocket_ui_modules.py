"""Held-out tests for bip-tornado-10 (never shown to the model).

The visible test renders a plain template from on_message. These render one
that uses the application's UI modules and UI methods, which live on the same
handler state that was being cleared too early.
"""
from tornado.template import DictLoader
from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.web import Application, RequestHandler, UIModule
from tornado.websocket import WebSocketHandler, websocket_connect


class Bold(UIModule):
    def render(self, text):
        return "<b>%s</b>" % text


def shout(handler, text):
    return text.upper()


class RenderModules(WebSocketHandler):
    def on_message(self, message):
        self.write_message(self.render_string("m.html", message=message))


class HeldOutUIModuleTest(AsyncHTTPTestCase):
    def get_app(self):
        return Application(
            [("/render", RenderModules)],
            template_path="heldout-tornado-10",  # its own loader cache entry
            template_loader=DictLoader({"m.html": "{% module Bold(message) %}|{{ shout(message) }}"}),
            ui_modules={"Bold": Bold},
            ui_methods={"shout": shout},
        )

    def tearDown(self):
        super(HeldOutUIModuleTest, self).tearDown()
        RequestHandler._template_loaders.clear()

    @gen_test
    def test_ui_modules_and_methods_render_in_on_message(self):
        ws = yield websocket_connect("ws://127.0.0.1:%d/render" % self.get_http_port())
        ws.write_message("hi")
        self.assertEqual((yield ws.read_message()), "<b>hi</b>|HI")
        ws.close()
