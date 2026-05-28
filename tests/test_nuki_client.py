"""Tests for nukiblinker.nuki_client — mock httpx."""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from nukiblinker.nuki_client import NukiClient


@pytest.fixture
def client():
    return NukiClient("10.0.0.1", 8080, "test-token")


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


class TestListCallbacks:
    @pytest.mark.asyncio
    async def test_returns_callbacks(self, client):
        resp = _mock_response({"callbacks": [{"id": 1, "url": "http://x"}]})
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.list_callbacks()
            assert result == [{"id": 1, "url": "http://x"}]

    @pytest.mark.asyncio
    async def test_empty_callbacks(self, client):
        resp = _mock_response({"callbacks": []})
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.list_callbacks()
            assert result == []


class TestRegisterCallback:
    @pytest.mark.asyncio
    async def test_registers_new_callback(self, client):
        list_resp = _mock_response({"callbacks": []})
        add_resp = _mock_response({"success": True, "id": 42})

        mock_http = MagicMock()
        mock_http.get = AsyncMock(side_effect=[list_resp, add_resp])

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.register_callback("http://me:8080/nuki/callback")
            assert result == 42

    @pytest.mark.asyncio
    async def test_skips_if_already_registered(self, client):
        list_resp = _mock_response({"callbacks": [{"id": 5, "url": "http://me:8080/nuki/callback"}]})

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=list_resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.register_callback("http://me:8080/nuki/callback")
            assert result == 5


class TestRemoveCallback:
    @pytest.mark.asyncio
    async def test_removes_callback(self, client):
        resp = _mock_response({"success": True})
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.remove_callback(42)
            assert result is True


class TestListDevices:
    @pytest.mark.asyncio
    async def test_lists_devices(self, client):
        devices = [{"nukiId": 1, "deviceType": 2, "name": "Opener"}]
        resp = _mock_response(devices)
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.list_devices()
            assert result[0]["name"] == "Opener"


class TestGetLastLog:
    @pytest.mark.asyncio
    async def test_returns_latest_entry(self, client):
        logs = [{"name": "Nico", "action": 3, "trigger": 2}]
        resp = _mock_response(logs)
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.get_last_log(12345)
            assert result["name"] == "Nico"

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_log(self, client):
        resp = _mock_response([])
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.get_last_log(12345)
            assert result is None
