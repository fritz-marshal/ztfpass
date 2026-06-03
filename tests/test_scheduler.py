"""Unit test for the paramiko-based forwarder — paramiko + http.client are
faked, so it verifies the orchestration (connect → channel → HTTP → parse)
without a real SSH tunnel or scheduler. The real tunnel path is validated
against the live scheduler on the host."""

from __future__ import annotations

from ztfpass import scheduler
from ztfpass.config import ZTFTunnel

TUNNEL = ZTFTunnel(
    mountain_ip="mountain.example",
    mountain_port=22,
    mountain_username="ztf",
    mountain_password="pw",
    mountain_bind_ip="10.0.0.5",
    mountain_bind_port=9999,
)


class _FakeChan:
    def settimeout(self, _t):
        pass


class _FakeTransport:
    last = None

    def __init__(self, addr):
        self.addr = addr
        self.connected = None
        self.opened = None
        self.closed = False
        _FakeTransport.last = self

    def connect(self, username=None, password=None):
        self.connected = (username, password)

    def open_channel(self, kind, dest, src, timeout=None):
        self.opened = (kind, dest, src)
        return _FakeChan()

    def close(self):
        self.closed = True


class _FakeResp:
    def __init__(self, status, body, headers):
        self.status, self._body, self._headers = status, body, headers

    def read(self):
        return self._body

    def getheaders(self):
        return list(self._headers.items())


class _FakeConn:
    last = None
    _resp = (200, b'{"ok": true}', {"queue_name": "ToO_x"})

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.sock = host, port, None
        self.req = None
        _FakeConn.last = self

    def request(self, method, path, body=None, headers=None):
        self.req = {"method": method, "path": path, "body": body, "headers": headers}

    def getresponse(self):
        return _FakeResp(*self._resp)


def _patch(monkeypatch):
    monkeypatch.setattr(scheduler.paramiko, "Transport", _FakeTransport)
    monkeypatch.setattr(scheduler, "HTTPConnection", _FakeConn)


def test_forward_connects_opens_channel_and_parses(monkeypatch):
    _patch(monkeypatch)
    client = scheduler.SSHTunnelSchedulerClient(TUNNEL, path="/queues", timeout=7)
    res = client.forward("PUT", {"queue_name": "ToO_x", "user": "obs"})

    t = _FakeTransport.last
    assert t.addr == ("mountain.example", 22)
    assert t.connected == ("ztf", "pw")
    # channel forwards to the scheduler bind address on the far side
    assert t.opened == ("direct-tcpip", ("10.0.0.5", 9999), ("127.0.0.1", 0))
    assert t.closed is True  # transport always closed

    c = _FakeConn.last
    assert c.sock is not None  # the channel was wired in as the socket
    assert c.req["method"] == "PUT" and c.req["path"] == "/queues"
    assert b'"queue_name": "ToO_x"' in c.req["body"]

    assert res.status == 200
    assert res.json == {"ok": True}
    assert res.headers == {"queue_name": "ToO_x"}


def test_forward_requires_complete_tunnel():
    client = scheduler.SSHTunnelSchedulerClient(ZTFTunnel())  # nothing configured
    try:
        client.forward("GET", {})
    except RuntimeError as e:
        assert "not fully configured" in str(e)
    else:
        raise AssertionError("expected RuntimeError for incomplete tunnel")


def test_forward_tolerates_non_json_body(monkeypatch):
    _patch(monkeypatch)
    _FakeConn._resp = (500, b"<html>oops</html>", {})
    try:
        res = scheduler.SSHTunnelSchedulerClient(TUNNEL).forward("GET", {})
        assert res.status == 500 and res.json is None
    finally:
        _FakeConn._resp = (200, b'{"ok": true}', {"queue_name": "ToO_x"})
