"""Tests for nukiblinker.discovery — mock external APIs."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nukiblinker.discovery import (
    discover_nuki_bridges,
    discover_hue_bridges,
    discover_chromecast_speakers,
)


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


class TestDiscoverNukiBridges:
    @pytest.mark.asyncio
    async def test_returns_bridges(self):
        data = {"bridges": [{"bridgeId": 1, "ip": "10.0.0.1", "port": 8080}]}
        resp = _mock_response(data)
        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await discover_nuki_bridges()
            assert len(result) == 1
            assert result[0]["ip"] == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = MagicMock()
            mock_http.get = AsyncMock(side_effect=Exception("network"))
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await discover_nuki_bridges()
            assert result == []


class TestDiscoverHueBridges:
    @pytest.mark.asyncio
    async def test_returns_bridges(self):
        data = [{"id": "abc", "internalipaddress": "10.0.0.2"}]
        resp = _mock_response(data)
        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await discover_hue_bridges()
            assert len(result) == 1
            assert "10.0.0.2" in result[0]["ip"]


class TestDiscoverChromecast:
    @pytest.mark.asyncio
    async def test_delegates_to_client(self):
        with patch("nukiblinker.chromecast_client.ChromecastClient") as mock_cls:
            mock_cls.return_value.list_speakers = AsyncMock(
                return_value=[{"name": "Nest", "ip": "10.0.0.5", "port": 8009, "type": "chromecast"}]
            )
            result = await discover_chromecast_speakers()
            assert len(result) == 1
            assert result[0]["name"] == "Nest"
