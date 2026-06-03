"""Passthrough to the ZTF scheduler queue API over an SSH tunnel.

Mirrors what Kowalski's ZTFTriggerHandler did: open an SSH tunnel to the
mountain (the scheduler host at Caltech) and forward the request to the
scheduler's queue endpoint (default `/queues`).

`SchedulerClient` is a tiny protocol so the FastAPI app can be tested with a
fake forwarder — no real tunnel, no real scheduler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import requests

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
    """Production client: SSH-tunnel to the mountain, then HTTP to the scheduler.
    `sshtunnel` is imported lazily so the package imports without it."""

    def __init__(
        self, tunnel: ZTFTunnel, *, path: str = "/queues", timeout: float = 10.0
    ):
        self._t = tunnel
        self._path = path if path.startswith("/") else f"/{path}"
        self._timeout = timeout

    def forward(self, method: str, json_body: dict | None) -> SchedulerResult:
        if not self._t.complete():
            raise RuntimeError(
                "ZTF tunnel not fully configured (need mountain_ip/port/username/"
                "password/bind_ip/bind_port)"
            )
        from sshtunnel import SSHTunnelForwarder

        server = SSHTunnelForwarder(
            (self._t.mountain_ip, self._t.mountain_port),
            ssh_username=self._t.mountain_username,
            ssh_password=self._t.mountain_password,
            remote_bind_address=(self._t.mountain_bind_ip, self._t.mountain_bind_port),
        )
        server.start()
        try:
            url = (
                f"http://{server.local_bind_host}:{server.local_bind_port}{self._path}"
            )
            resp = requests.request(
                method, url, json=json_body or {}, timeout=self._timeout
            )
            try:
                data = resp.json()
            except ValueError:
                data = None
            return SchedulerResult(
                status=resp.status_code, json=data, headers=dict(resp.headers)
            )
        finally:
            server.stop()
