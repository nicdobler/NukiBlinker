"""Tests for lifecycle — startup registration, shutdown deregistration, build_clients."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from nukiblinker.config import AppConfig
from nukiblinker.__main__ import (
    _build_clients, _register_callback_loop, _resolve_callback_url,
    _deregister_callback, Clients,
)


class TestBuildClients:
    def test_nuki_client_created_when_configured(self):
        cfg = AppConfig()
        cfg.nuki.bridge_ip = "10.0.0.1"
        cfg.nuki.api_token = "tok"
        clients = _build_clients(cfg)
        assert clients.nuki is not None

    def test_nuki_client_none_when_not_configured(self):
        cfg = AppConfig()
        clients = _build_clients(cfg)
        assert clients.nuki is None

    def test_hue_client_created_when_configured(self):
        cfg = AppConfig()
        cfg.hue.bridge_ip = "10.0.0.2"
        cfg.hue.api_key = "key"
        clients = _build_clients(cfg)
        assert clients.hue is not None

    def test_hue_client_none_when_not_configured(self):
        cfg = AppConfig()
        clients = _build_clients(cfg)
        assert clients.hue is None

    def test_chromecast_and_airplay_always_created(self):
        cfg = AppConfig()
        clients = _build_clients(cfg)
        assert clients.chromecast is not None
        assert clients.airplay is not None

    def test_homekit_created_when_enabled(self):
        cfg = AppConfig()
        cfg.homekit.enabled = True
        clients = _build_clients(cfg)
        assert clients.homekit is not None

    def test_homekit_none_when_disabled(self):
        cfg = AppConfig()
        clients = _build_clients(cfg)
        assert clients.homekit is None


class TestResolveCallbackUrl:
    def test_uses_explicit_host(self):
        cfg = AppConfig()
        cfg.nuki.bridge_ip = "10.0.0.1"
        cfg.server.host = "10.0.0.5"
        cfg.server.port = 8080
        assert _resolve_callback_url(cfg) == "http://10.0.0.5:8080/nuki/callback"

    def test_auto_detects_when_bind_all(self):
        cfg = AppConfig()
        cfg.nuki.bridge_ip = "10.0.0.1"
        cfg.server.host = "0.0.0.0"
        cfg.server.port = 8080
        url = _resolve_callback_url(cfg)
        # Should not contain 0.0.0.0
        assert "0.0.0.0" not in url
        assert url.endswith(":8080/nuki/callback")


class TestRegisterCallbackLoop:
    @pytest.mark.asyncio
    async def test_registers_on_first_attempt(self):
        clients = Clients()
        clients.nuki = AsyncMock()
        clients.nuki.register_callback.return_value = 42
        cfg = AppConfig()
        cfg.nuki.bridge_ip = "10.0.0.1"
        cfg.server.host = "10.0.0.5"
        cfg.server.port = 8080
        app = MagicMock()
        app.state = MagicMock()

        await _register_callback_loop(cfg, clients, app)
        clients.nuki.register_callback.assert_called_once()
        assert app.state.callback_id == 42

    @pytest.mark.asyncio
    async def test_skips_when_nuki_not_configured(self):
        clients = Clients()
        cfg = AppConfig()
        app = MagicMock()
        app.state = MagicMock()

        await _register_callback_loop(cfg, clients, app)
        # Should return immediately without setting callback_id

    @pytest.mark.asyncio
    async def test_retries_on_error_then_succeeds(self):
        clients = Clients()
        clients.nuki = AsyncMock()
        clients.nuki.register_callback.side_effect = [Exception("fail"), 99]
        cfg = AppConfig()
        cfg.nuki.bridge_ip = "10.0.0.1"
        cfg.server.host = "10.0.0.5"
        cfg.server.port = 8080
        app = MagicMock()
        app.state = MagicMock()

        # Patch sleep to avoid real delays
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(asyncio, "sleep", AsyncMock())
            await _register_callback_loop(cfg, clients, app)

        assert clients.nuki.register_callback.call_count == 2
        assert app.state.callback_id == 99


class TestDeregisterCallback:
    @pytest.mark.asyncio
    async def test_deregisters(self):
        clients = Clients()
        clients.nuki = AsyncMock()
        await _deregister_callback(clients, 42)
        clients.nuki.remove_callback.assert_called_once_with(42)

    @pytest.mark.asyncio
    async def test_skips_when_no_nuki(self):
        clients = Clients()
        await _deregister_callback(clients, 42)  # should not raise

    @pytest.mark.asyncio
    async def test_skips_when_no_callback_id(self):
        clients = Clients()
        clients.nuki = AsyncMock()
        await _deregister_callback(clients, None)
        clients.nuki.remove_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_error_gracefully(self):
        clients = Clients()
        clients.nuki = AsyncMock()
        clients.nuki.remove_callback.side_effect = Exception("network")
        await _deregister_callback(clients, 42)  # should not raise
