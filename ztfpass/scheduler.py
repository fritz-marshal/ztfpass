"""Passthrough to the ZTF scheduler queue API over an SSH tunnel.

Mirrors what Kowalski did — SSH to the mountain (the scheduler host) and forward
the HTTP request to the scheduler's queue endpoint (default ``/queues``) — but
opens the tunnel with **paramiko directly** (a ``direct-tcpip`` channel used as
the HTTP socket) instead of the unmaintained ``sshtunnel`` wrapper. That keeps
us on modern paramiko with no extra dependency and no version pin.

``SchedulerClient`` is a tiny protocol so the FastAPI app can be tested with a
fake forwarder — no real tunnel, no real scheduler.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from http.client import HTTPConnection
from typing import Any, Protocol, runtime_checkable

import paramiko

from .config import ZTFTunnel


@dataclass
class SchedulerResult:
    status: int
    json: Any | None = None
    headers: dict = field(default_factory=dict)


@runtime_checkable
class SchedulerClient(Protocol):
    def forward(self, method: str, json_body: dict | None) -> SchedulerResult:
        """Forward an HTTP method + JSON body to the scheduler queue endpoint."""
        ...


class SSHTunnelSchedulerClient:
    """Production client: open a paramiko SSH transport to the mountain, then a
    ``direct-tcpip`` channel to the scheduler and speak HTTP over it."""

    def __init__(
        self, tunnel: ZTFTunnel, *, path: str = "/queues", timeout: float = 10.0
    ):
        self._t = tunnel
        self._path = path if path.startswith("/") else f"/{path}"
        self._timeout = timeout

    def forward(self, method: str, json_body: dict | None) -> SchedulerResult:
        t = self._t
        if not t.complete():
            raise RuntimeError(
                "ZTF tunnel not fully configured (need mountain_ip/port/username/"
                "password/bind_ip/bind_port)"
            )

        transport = paramiko.Transport((t.mountain_ip, int(t.mountain_port)))
        transport.banner_timeout = self._timeout
        try:
            transport.connect(
                username=t.mountain_username, password=t.mountain_password
            )
            # A direct-tcpip channel is socket-like; hand it to http.client as the
            # connection's socket so we tunnel a normal HTTP request to the
            # scheduler's bind address on the far side.
            chan = transport.open_channel(
                "direct-tcpip",
                (t.mountain_bind_ip, int(t.mountain_bind_port)),
                ("127.0.0.1", 0),
                timeout=self._timeout,
            )
            chan.settimeout(self._timeout)
            conn = HTTPConnection(
                t.mountain_bind_ip, int(t.mountain_bind_port), timeout=self._timeout
            )
            conn.sock = chan
            body = _json.dumps(json_body or {}).encode()
            conn.request(
                method,
                self._path,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            resp = conn.getresponse()
            raw = resp.read()
            headers = dict(resp.getheaders())
            try:
                data = _json.loads(raw) if raw else None
            except ValueError:
                data = None
            return SchedulerResult(status=resp.status, json=data, headers=headers)
        finally:
            transport.close()
