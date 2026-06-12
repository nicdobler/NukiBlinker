"""Tests for nukiblinker.server — callback endpoint routing."""

from unittest.mock import MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

from nukiblinker.config import AppConfig
from nukiblinker.server import create_app


def _make_clients():
    clients = MagicMock()
    clients.hue = AsyncMock()
    clients.chromecast = AsyncMock()
    clients.airplay = AsyncMock()
    clients.homekit = AsyncMock()
    clients.nuki = AsyncMock()
    # Real deduplicator so duplicate detection behaves predictably in tests
    from nukiblinker.deduplication import Deduplicator
    clients.deduplicator = Deduplicator(window_seconds=120)
    return clients


def _ring_payload(nuki_id=100, ts="2026-06-12T13:51:05+00:00"):
    return {
        "deviceType": 2, "nukiId": nuki_id, "state": 1,
        "ringactionState": True, "ringactionTimestamp": ts,
    }


@pytest.fixture
def app():
    config = AppConfig()
    clients = _make_clients()
    return create_app(config, clients)


@pytest.fixture
def client(app):
    return TestClient(app)


class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestNukiCallback:
    def test_ring_event(self, client):
        r = client.post("/nuki/callback", json=_ring_payload())
        assert r.status_code == 200
        assert r.json()["event"] == "ring"

    def test_ring_to_open_event(self, client):
        payload = {"deviceType": 2, "nukiId": 100, "state": 7}
        r = client.post("/nuki/callback", json=payload)
        assert r.status_code == 200
        assert r.json()["event"] == "ring_to_open"

    def test_door_opened_event(self, client):
        payload = {"deviceType": 0, "nukiId": 200, "state": 5}
        r = client.post("/nuki/callback", json=payload)
        assert r.status_code == 200
        assert r.json()["event"] == "door_opened"

    def test_ignored_event(self, client):
        payload = {"deviceType": 2, "nukiId": 100, "state": 3}
        r = client.post("/nuki/callback", json=payload)
        assert r.status_code == 200
        assert r.json()["status"] == "ignored"

    def test_state_1_online_ignored(self, client):
        """#97: bare Opener state==1 (online) is not a ring."""
        payload = {"deviceType": 2, "nukiId": 100, "state": 1}
        r = client.post("/nuki/callback", json=payload)
        assert r.status_code == 200
        assert r.json()["status"] == "ignored"

    def test_unknown_device_type(self, client):
        payload = {"deviceType": 99, "nukiId": 100, "state": 1}
        r = client.post("/nuki/callback", json=payload)
        assert r.status_code == 200
        assert r.json()["status"] == "ignored"

    def test_paused_ignores_callback(self, app, client):
        app.state.paused = True
        r = client.post("/nuki/callback", json=_ring_payload())
        assert r.status_code == 200
        assert r.json()["status"] == "paused"

    def test_invalid_payload(self, client):
        r = client.post("/nuki/callback", content=b"not json", headers={"content-type": "application/json"})
        assert r.status_code == 400

    def test_records_last_event(self, app, client):
        client.post("/nuki/callback", json=_ring_payload())
        assert app.state.last_event is not None
        assert app.state.last_event["type"] == "ring"

    def test_duplicate_ring_suppressed(self, client):
        """#97: a repeated callback for the same ring is suppressed."""
        payload = _ring_payload(ts="2026-06-12T13:51:05+00:00")
        first = client.post("/nuki/callback", json=payload)
        assert first.json()["event"] == "ring"
        second = client.post("/nuki/callback", json=payload)
        assert second.json()["status"] == "duplicate"

    def test_second_distinct_ring_not_suppressed(self, client):
        """#97: a genuine second ring (new ringactionTimestamp) still notifies."""
        client.post("/nuki/callback", json=_ring_payload(ts="2026-06-12T13:51:05+00:00"))
        second = client.post("/nuki/callback", json=_ring_payload(ts="2026-06-12T13:51:40+00:00"))
        assert second.json()["event"] == "ring"
