"""Tests for lifecycle — startup registration, shutdown deregistration, build_clients."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nukiblinker.config import AppConfig
from nukiblinker.__main__ import _build_clients, _register_callback, _deregister_callback, Clients


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


class TestRegisterCallback:
    @pytest.mark.asyncio
    async def test_registers_when_nuki_configured(self):
        clients = Clients()
        clients.nuki = AsyncMock()
        clients.nuki.register_callback.return_value = 42
        cfg = AppConfig()
        cfg.server.host = "10.0.0.5"
        cfg.server.port = 8080

        result = await _register_callback(cfg, clients)
        assert result == 42

    @pytest.mark.asyncio
    async def test_skips_when_nuki_not_configured(self):
        clients = Clients()
        cfg = AppConfig()
        result = await _register_callback(cfg, clients)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        clients = Clients()
        clients.nuki = AsyncMock()
        clients.nuki.register_callback.side_effect = Exception("fail")
        cfg = AppConfig()
        result = await _register_callback(cfg, clients)
        assert result is None


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
