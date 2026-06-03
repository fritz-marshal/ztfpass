"""Configuration for ztfpass.

Loads a YAML file (path from $ZTFPASS_CONFIG, default ./config.yaml) and lets
environment variables override the secret-bearing fields, so secrets need not
live in the YAML. Mirrors the keys Kowalski used under `config["ztf"]`.

YAML shape:

    ztf:                       # SSH tunnel to the mountain (ZTF scheduler host)
      mountain_ip: ...
      mountain_port: 22
      mountain_username: ...
      mountain_password: ...
      mountain_bind_ip: 127.0.0.1     # scheduler bind addr on the far side
      mountain_bind_port: ...
    scheduler:
      path: /queues            # endpoint on the scheduler the tunnel forwards to
      timeout: 10
    auth:
      tokens: [ "<bearer token SkyPortal sends>" ]

Env overrides: ZTFPASS_CONFIG, ZTFPASS_AUTH_TOKENS (comma-sep),
ZTF_MOUNTAIN_IP / _PORT / _USERNAME / _PASSWORD / _BIND_IP / _BIND_PORT.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ZTFTunnel:
    mountain_ip: str | None = None
    mountain_port: int | None = None
    mountain_username: str | None = None
    mountain_password: str | None = None
    mountain_bind_ip: str | None = None
    mountain_bind_port: int | None = None

    def complete(self) -> bool:
        return all(
            v is not None
            for v in (
                self.mountain_ip,
                self.mountain_port,
                self.mountain_username,
                self.mountain_password,
                self.mountain_bind_ip,
                self.mountain_bind_port,
            )
        )


@dataclass
class Settings:
    ztf: ZTFTunnel = field(default_factory=ZTFTunnel)
    scheduler_path: str = "/queues"
    scheduler_timeout: float = 10.0
    tokens: list[str] = field(default_factory=list)


def _int_or_none(v):
    return int(v) if v not in (None, "") else None


def load_settings(path: str | os.PathLike | None = None) -> Settings:
    path = path or os.environ.get("ZTFPASS_CONFIG", "config.yaml")
    raw: dict = {}
    p = Path(path)
    if p.exists():
        raw = yaml.safe_load(p.read_text()) or {}

    z = raw.get("ztf") or {}
    sched = raw.get("scheduler") or {}
    auth = raw.get("auth") or {}

    tunnel = ZTFTunnel(
        mountain_ip=os.environ.get("ZTF_MOUNTAIN_IP", z.get("mountain_ip")),
        mountain_port=_int_or_none(
            os.environ.get("ZTF_MOUNTAIN_PORT", z.get("mountain_port"))
        ),
        mountain_username=os.environ.get(
            "ZTF_MOUNTAIN_USERNAME", z.get("mountain_username")
        ),
        mountain_password=os.environ.get(
            "ZTF_MOUNTAIN_PASSWORD", z.get("mountain_password")
        ),
        mountain_bind_ip=os.environ.get(
            "ZTF_MOUNTAIN_BIND_IP", z.get("mountain_bind_ip")
        ),
        mountain_bind_port=_int_or_none(
            os.environ.get("ZTF_MOUNTAIN_BIND_PORT", z.get("mountain_bind_port"))
        ),
    )

    tokens = list(auth.get("tokens") or [])
    env_tokens = os.environ.get("ZTFPASS_AUTH_TOKENS")
    if env_tokens:
        tokens = [t.strip() for t in env_tokens.split(",") if t.strip()]

    return Settings(
        ztf=tunnel,
        scheduler_path=sched.get("path", "/queues"),
        scheduler_timeout=float(sched.get("timeout", 10.0)),
        tokens=tokens,
    )
