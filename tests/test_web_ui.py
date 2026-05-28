"""Tests for nukiblinker.web_ui — API routes + localhost access control."""

from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from nukiblinker.config import AppConfig
from nukiblinker.server import create_app
from nukiblinker.web_ui import mount_web_ui


def _make_clients():
    clients = MagicMock()
    clients.hue = AsyncMock()
    clients.chromecast = AsyncMock()
    clients.airplay = AsyncMock()
    clients.homekit = AsyncMock()
    clients.nuki = AsyncMock()
    return clients


@pytest.fixture
def app(tmp_path):
    config = AppConfig()
    config.nuki.api_token = "secret-token"
    config.hue.api_key = "secret-key"
    clients = _make_clients()
    application = create_app(config, clients)
    config_path = str(tmp_path / "config.yaml")
    mount_web_ui(application, config_path)
    # Allow TestClient's "testclient" host through the localhost guard
    application.state.allowed_hosts = {"127.0.0.1", "::1", "localhost", "testclient"}
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


class TestGetConfig:
    def test_returns_masked_config(self, client):
        r = client.get("/api/config")
        assert r.status_code == 200
        data = r.json()
        assert data["nuki"]["api_token"] == "***"
        assert data["hue"]["api_key"] == "***"

    def test_includes_event_rules(self, client):
        r = client.get("/api/config")
        data = r.json()
        assert "events" in data
        assert "ring" in data["events"]
        assert "ring_to_open" in data["events"]
        assert "door_opened" in data["events"]


class TestPutConfig:
    def test_saves_valid_config(self, client):
        new_cfg = AppConfig()
        new_cfg.server.port = 9090
        r = client.put("/api/config", json=new_cfg.model_dump(mode="json"))
        assert r.status_code == 200
        assert r.json()["status"] == "saved"

    def test_rejects_invalid_config(self, client):
        r = client.put("/api/config", json={"server": {"port": "invalid"}})
        assert r.status_code == 400


class TestStatus:
    def test_returns_status(self, client):
        r = client.get("/api/status")
        assert r.status_code == 200
        assert r.json()["paused"] is False


class TestPauseResume:
    def test_pause(self, app, client):
        r = client.post("/api/pause")
        assert r.status_code == 200
        assert app.state.paused is True

    def test_resume(self, app, client):
        app.state.paused = True
        r = client.post("/api/resume")
        assert r.status_code == 200
        assert app.state.paused is False


class TestTestEvent:
    def test_fire_ring(self, client):
        with patch("nukiblinker.web_ui.event_router") as mock_er:
            mock_er.dispatch = AsyncMock()
            r = client.post("/api/test/event/ring")
            assert r.status_code == 200
            assert r.json()["event"] == "ring"

    def test_unknown_event_type(self, client):
        r = client.post("/api/test/event/unknown")
        assert r.status_code == 400


class TestLocalhostGuard:
    """Verify non-localhost requests to /api/ are blocked."""

    def test_blocked_when_not_localhost(self, tmp_path):
        """Create an app WITHOUT testclient in allowed_hosts."""
        config = AppConfig()
        clients = _make_clients()
        strict_app = create_app(config, clients)
        mount_web_ui(strict_app, str(tmp_path / "config.yaml"))
        # Do NOT add "testclient" to allowed_hosts
        strict_client = TestClient(strict_app)
        r = strict_client.get("/api/status")
        assert r.status_code == 403

    def test_health_accessible_from_anywhere(self, tmp_path):
        """Health endpoint is NOT under /api/ so it bypasses the guard."""
        config = AppConfig()
        clients = _make_clients()
        strict_app = create_app(config, clients)
        mount_web_ui(strict_app, str(tmp_path / "config.yaml"))
        strict_client = TestClient(strict_app)
        r = strict_client.get("/health")
        assert r.status_code == 200
