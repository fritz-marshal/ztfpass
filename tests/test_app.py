"""Tests for the passthrough — a fake SchedulerClient stands in for the SSH
tunnel + ZTF scheduler, so no network/tunnel is touched."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ztfpass.app import create_app
from ztfpass.config import Settings, ZTFTunnel
from ztfpass.scheduler import SchedulerResult

TOKEN = "test-token"

TRIGGER = {
    "queue_name": "ToO_GRB260603A",
    "validity_window_mjd": [60829.0, 60829.5],
    "targets": [
        {
            "field_id": 600,
            "filter_id": 1,
            "program_id": 2,
            "program_pi": "Kulkarni/obs",
            "exposure_time": 30,
        }
    ],
    "queue_type": "list",
    "user": "obs",
}
DELETE = {"queue_name": "ToO_GRB260603A", "user": "obs"}


class FakeScheduler:
    """Records forwards; returns a queued SchedulerResult (or a default 200)."""

    def __init__(self):
        self.calls = []
        self.queue = []

    def push(self, status, json=None, headers=None):
        self.queue.append(SchedulerResult(status, json, headers or {}))

    def forward(self, method, json_body):
        self.calls.append((method, json_body))
        return self.queue.pop(0) if self.queue else SchedulerResult(200, {}, {})


def _client(fake):
    settings = Settings(ztf=ZTFTunnel(), tokens=[TOKEN])
    return TestClient(create_app(settings=settings, client=fake)), fake


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


# ── auth ──────────────────────────────────────────────────────────────────────
def test_missing_token_401():
    c, _ = _client(FakeScheduler())
    r = c.get("/api/triggers/ztf")
    assert r.status_code == 401 and r.json()["status"] == "error"


def test_bad_token_401():
    c, _ = _client(FakeScheduler())
    r = c.get("/api/triggers/ztf", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


# ── GET queue ─────────────────────────────────────────────────────────────────
def test_get_queue_success():
    fake = FakeScheduler()
    fake.push(200, json=[{"queue_name": "ToO_x"}])
    c, fake = _client(fake)
    r = c.get("/api/triggers/ztf", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success" and body["message"] == "retrieved"
    assert body["data"] == [{"queue_name": "ToO_x"}]
    assert fake.calls[0][0] == "GET"


def test_get_queue_scheduler_error():
    fake = FakeScheduler()
    fake.push(500, json={"err": "boom"})
    c, _ = _client(fake)
    r = c.get("/api/triggers/ztf", headers=_auth())
    assert r.status_code == 400 and r.json()["status"] == "error"


# ── PUT trigger ───────────────────────────────────────────────────────────────
def test_put_trigger_submitted():
    fake = FakeScheduler()
    fake.push(201, headers={"queue_name": "ToO_GRB260603A"})
    c, fake = _client(fake)
    r = c.put("/api/triggers/ztf", json=TRIGGER, headers=_auth())
    assert r.status_code == 200
    assert r.json()["message"] == "submitted"
    method, fwd = fake.calls[0]
    assert method == "PUT" and fwd["queue_name"] == "ToO_GRB260603A"


def test_put_trigger_already_exists_409():
    fake = FakeScheduler()
    fake.push(200, headers={"queue_name": "ToO_GRB260603A"})
    c, _ = _client(fake)
    r = c.put("/api/triggers/ztf", json=TRIGGER, headers=_auth())
    assert r.status_code == 409
    assert "already exists" in r.json()["message"]


def test_put_trigger_rejected():
    fake = FakeScheduler()
    fake.push(400, json={"error": "bad field"})
    c, _ = _client(fake)
    r = c.put("/api/triggers/ztf", json=TRIGGER, headers=_auth())
    assert r.status_code == 400 and "rejected" in r.json()["message"]


def test_put_trigger_invalid_payload_not_forwarded():
    fake = FakeScheduler()
    c, fake = _client(fake)
    r = c.put(
        "/api/triggers/ztf", json={"queue_name": "x"}, headers=_auth()
    )  # missing fields
    assert r.status_code == 400
    assert fake.calls == []  # never forwarded


# ── DELETE ────────────────────────────────────────────────────────────────────
def test_delete_success():
    fake = FakeScheduler()
    fake.push(200, headers={"queue_name": "ToO_GRB260603A"})
    c, fake = _client(fake)
    r = c.request("DELETE", "/api/triggers/ztf", json=DELETE, headers=_auth())
    assert r.status_code == 200 and r.json()["message"] == "deleted"
    assert fake.calls[0][0] == "DELETE"


def test_delete_rejected():
    fake = FakeScheduler()
    fake.push(404, json={"error": "no such queue"})
    c, _ = _client(fake)
    r = c.request("DELETE", "/api/triggers/ztf", json=DELETE, headers=_auth())
    assert r.status_code == 400 and "rejected" in r.json()["message"]


# ── .test (validate, never forward) ───────────────────────────────────────────
def test_put_test_does_not_forward():
    fake = FakeScheduler()
    c, fake = _client(fake)
    r = c.put("/api/triggers/ztf.test", json=TRIGGER, headers=_auth())
    assert r.status_code == 200 and r.json()["message"] == "submitted"
    assert fake.calls == []


def test_healthz_open():
    c, _ = _client(FakeScheduler())
    r = c.get("/healthz")  # no auth
    assert r.status_code == 200 and r.json()["data"]["tunnel_configured"] is False
