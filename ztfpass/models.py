"""Request bodies — same shape Kowalski's ZTFTrigger / ZTFDelete validated."""

from __future__ import annotations

from pydantic import BaseModel


class ZTFTrigger(BaseModel):
    queue_name: str
    validity_window_mjd: list[float]
    targets: list[dict]
    queue_type: str
    user: str


class ZTFDelete(BaseModel):
    queue_name: str
    user: str
