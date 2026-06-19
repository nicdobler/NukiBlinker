"""Tests for nukiblinker.nuki_web_client — mock httpx."""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from nukiblinker.nuki_web_client import NukiWebClient, TRIGGER_NAMES


@pytest.fixture
def client():
    return NukiWebClient("web-token")


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


class TestGetRecentLog:
    @pytest.mark.asyncio
    async def test_returns_entries(self, client):
        entries = [{"smartlockId": 1, "name": "Nico", "trigger": 2}]
        resp = _mock_response(entries)
        mock_http = MagicMock(get=AsyncMock(return_value=resp))
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.get_recent_log(smartlock_id=1, limit=20)
            assert result == entries
            # Bearer auth header is set
            _, kwargs = mock_http.get.call_args
            assert kwargs["headers"]["Authorization"] == "Bearer web-token"

    @pytest.mark.asyncio
    async def test_non_list_response_returns_empty(self, client):
        resp = _mock_response({"error": "nope"})
        mock_http = MagicMock(get=AsyncMock(return_value=resp))
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            assert await client.get_recent_log() == []

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self, client):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(side_effect=Exception("boom"))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            assert await client.get_recent_log() == []


def test_trigger_names_has_button():
    assert TRIGGER_NAMES[2] == "button"


class TestListSmartlocks:
    """Tests for NukiWebClient.list_smartlocks() (#190)."""

    @pytest.mark.asyncio
    async def test_returns_device_list(self, client):
        devices = [
            {"smartlockId": 9129696002, "name": "Portal", "type": 2},
        ]
        resp = _mock_response(devices)
        mock_http = MagicMock(get=AsyncMock(return_value=resp))
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client.list_smartlocks()
            assert result == devices
            url_arg = mock_http.get.call_args.args[0]
            assert url_arg.endswith("/smartlock")

    @pytest.mark.asyncio
    async def test_non_list_response_returns_empty(self, client):
        resp = _mock_response({"error": "not a list"})
        mock_http = MagicMock(get=AsyncMock(return_value=resp))
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            assert await client.list_smartlocks() == []

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self, client):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(side_effect=Exception("boom"))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            assert await client.list_smartlocks() == []
