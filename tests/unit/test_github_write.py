"""Phase 6.2 — GitHub write path. Mocked transport, no real network."""

import httpx
import pytest

from cidra.integrations import github_write
from cidra.nodes.report import _MARKER

BODY = f"{_MARKER}\nhello"


def _mock(monkeypatch, handler, token="wtok"):
    monkeypatch.setattr(github_write, "GITHUB_TOKEN", token, raising=False)

    def fake_client():
        if not github_write.GITHUB_TOKEN:
            raise ValueError("CIDRA_GITHUB_TOKEN (write) is not set")
        return httpx.Client(base_url="https://api.github.com",
                            headers={"Authorization": f"Bearer {github_write.GITHUB_TOKEN}"},
                            transport=httpx.MockTransport(handler))

    monkeypatch.setattr(github_write, "_client", fake_client)


def test_posts_new_comment_when_none_exists(monkeypatch):
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"] = req.headers["Authorization"]
        if req.method == "GET":
            return httpx.Response(200, json=[])  # no existing comment
        seen["method"], seen["url"] = req.method, str(req.url)
        return httpx.Response(201, json={"html_url": "https://gh/c/1"})

    _mock(monkeypatch, handler)
    url = github_write.post_or_update_comment("o/r", 7, BODY)
    assert url == "https://gh/c/1"
    assert seen["method"] == "POST" and seen["url"].endswith("/issues/7/comments")
    assert seen["auth"] == "Bearer wtok"  # write token, not the RO one


def test_updates_existing_comment(monkeypatch):
    seen = {}

    def handler(req: httpx.Request):
        if req.method == "GET":
            return httpx.Response(200, json=[{"id": 99, "body": f"old {_MARKER}"}])
        seen["method"], seen["url"] = req.method, str(req.url)
        return httpx.Response(200, json={"html_url": "https://gh/c/99"})

    _mock(monkeypatch, handler)
    url = github_write.post_or_update_comment("o/r", 7, BODY)
    assert url == "https://gh/c/99"
    assert seen["method"] == "PATCH" and seen["url"].endswith("/issues/comments/99")


def test_finds_comment_on_a_later_page(monkeypatch):
    seen = {}

    def handler(req: httpx.Request):
        if req.method == "GET":
            page = int(req.url.params.get("page", "1"))
            if page == 1:
                return httpx.Response(200, json=[{"id": i, "body": "x"} for i in range(100)])
            return httpx.Response(200, json=[{"id": 250, "body": f"me {_MARKER}"}])
        seen["method"], seen["url"] = req.method, str(req.url)
        return httpx.Response(200, json={"html_url": "https://gh/c/250"})

    _mock(monkeypatch, handler)
    url = github_write.post_or_update_comment("o/r", 7, BODY)
    assert url == "https://gh/c/250"
    assert seen["method"] == "PATCH" and seen["url"].endswith("/issues/comments/250")


def test_refuses_body_without_marker(monkeypatch):
    _mock(monkeypatch, lambda req: httpx.Response(200, json=[]))
    with pytest.raises(ValueError, match="marker"):
        github_write.post_or_update_comment("o/r", 7, "no marker here")


def test_raises_without_write_token(monkeypatch):
    _mock(monkeypatch, lambda req: httpx.Response(200, json=[]), token="")
    with pytest.raises(ValueError, match="write"):
        github_write.post_or_update_comment("o/r", 7, BODY)
