"""Tests for nukiblinker.web_ui — API routes + localhost access control."""

from unittest.mock import MagicMock, AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from nukiblinker.config import AppConfig
from nukiblinker.server import create_app
from nukiblinker.web_ui import mount_web_ui, _bridge_error


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


class TestBridgeError:
    """Verify _bridge_error returns user-friendly messages and correct status."""

    def test_connect_timeout_returns_502(self):
        body, status = _bridge_error(httpx.ConnectTimeout("timed out"), "Nuki Bridge")
        assert status == 502
        assert "Nuki Bridge unreachable" in body["error"]
        assert "timed out" in body["error"]

    def test_connect_error_returns_502(self):
        body, status = _bridge_error(httpx.ConnectError("refused"), "Hue Bridge")
        assert status == 502
        assert "Hue Bridge unreachable" in body["error"]

    def test_http_401_returns_clear_auth_error(self):
        resp = httpx.Response(401, request=httpx.Request("GET", "http://x"))
        exc = httpx.HTTPStatusError("", request=resp.request, response=resp)
        body, status = _bridge_error(exc, "Nuki Bridge")
        assert status == 401
        assert "API token" in body["error"]

    def test_http_500_from_bridge_returns_502(self):
        resp = httpx.Response(500, request=httpx.Request("GET", "http://x"))
        exc = httpx.HTTPStatusError("", request=resp.request, response=resp)
        body, status = _bridge_error(exc, "Bridge")
        assert status == 502
        assert "HTTP 500" in body["error"]

    def test_generic_exception_returns_500_without_leaking_details(self):
        body, status = _bridge_error(ValueError("bad value"), "Bridge")
        assert status == 500
        assert body["error"] == "Unexpected bridge communication error"
        assert "bad value" not in body["error"]

    def test_empty_str_exception_uses_repr(self):
        """Regression: httpx.ConnectTimeout str() can be empty."""
        body, status = _bridge_error(httpx.ConnectTimeout(""), "Nuki Bridge")
        assert status == 502
        assert body["error"]  # must not be empty


class TestNukiPairTimeout:
    """Regression: POST /api/nuki/pair should return 502 on ConnectTimeout, not 500."""

    def test_returns_502_on_bridge_timeout(self, app, client):
        # Ensure Nuki is configured so the endpoint doesn't short-circuit with 400
        app.state.config.nuki.bridge_ip = "192.168.1.100"
        app.state.config.nuki.api_token = "test-token"
        with patch(
            "nukiblinker.nuki_client.NukiClient.list_callbacks",
            new_callable=AsyncMock, side_effect=httpx.ConnectTimeout(""),
        ):
            r = client.post("/api/nuki/pair")
            assert r.status_code == 502
            assert "Nuki Bridge unreachable" in r.json()["error"]


class TestPrivateNetworkGuard:
    """Verify non-private-network requests to /api/ are blocked."""

    def test_blocked_when_not_private(self, tmp_path):
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
