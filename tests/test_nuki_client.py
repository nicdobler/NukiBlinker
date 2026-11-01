"""Tests for nukiblinker.nuki_client — mock httpx."""

import logging
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from nukiblinker.nuki_client import NukiClient, _is_own_callback

CB_URL = "http://me:8080/nuki/callback"


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


class TestIsOwnCallback:
    @pytest.mark.parametrize("url,expected", [
        (CB_URL, True),
        ("http://10.0.0.9:8080/nuki/callback", True),
        ("http://10.0.0.9:8080/nuki/callback/", True),
        ("http://ha:8123/api/nuki", False),
        ("http://ha:8123/nuki/callback/extra", False),
        ("", False),
    ])
    def test_matches_only_callback_path(self, url, expected):
        assert _is_own_callback(url) is expected


class TestAddCallback:
    @pytest.mark.asyncio
    async def test_adds_callback(self, client):
        resp = _mock_response({"success": True, "id": 7})
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(get=AsyncMock(return_value=resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            assert await client._add_callback(CB_URL) == 7

    @pytest.mark.asyncio
    async def test_returns_none_on_bridge_failure(self, client):
        resp = _mock_response({"success": False, "message": "list full"})
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(get=AsyncMock(return_value=resp)))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            assert await client._add_callback(CB_URL) is None


class TestResetCallbacks:
    @pytest.mark.asyncio
    async def test_removes_only_own_callbacks(self, client):
        """Stale own-IP callback is removed (re-listing after each removal
        because Bridge ids may shift); foreign callbacks are preserved."""
        foreign = {"id": 2, "url": "http://ha:8123/api/nuki"}
        lists = [
            [{"id": 0, "url": CB_URL},
             {"id": 1, "url": "http://10.0.0.9:8080/nuki/callback"}, foreign],
            # After removing id 0 the old-IP callback shifted to id 0:
            [{"id": 0, "url": "http://10.0.0.9:8080/nuki/callback"}, foreign],
            [foreign],
            [foreign, {"id": 1, "url": CB_URL}],
        ]
        with patch.object(client, "list_callbacks",
                          new_callable=AsyncMock, side_effect=lists), \
             patch.object(client, "remove_callback",
                          new_callable=AsyncMock, return_value=True) as mock_rm, \
             patch.object(client, "_add_callback",
                          new_callable=AsyncMock, return_value=1) as mock_add:
            result = await client.reset_callbacks(CB_URL)

        removed_ids = [c.args[0] for c in mock_rm.await_args_list]
        assert removed_ids == [0, 0]
        mock_add.assert_awaited_once_with(CB_URL)
        assert result["verified"] is True
        assert result["removed"] == [0, 0]
        assert result["callback_id"] == 1

    @pytest.mark.asyncio
    async def test_verified_false_when_url_missing(self, client, caplog):
        """Bridge dropped the URL right after adding → verified False + warning."""
        lists = [
            [{"id": 0, "url": CB_URL}],
            [],
            [{"id": 5, "url": "http://ha:8123/api/nuki"}],
        ]
        with patch.object(client, "list_callbacks",
                          new_callable=AsyncMock, side_effect=lists), \
             patch.object(client, "remove_callback",
                          new_callable=AsyncMock, return_value=True), \
             patch.object(client, "_add_callback",
                          new_callable=AsyncMock, return_value=2):
            with caplog.at_level(logging.WARNING, logger="nuki_client"):
                result = await client.reset_callbacks(CB_URL)

        assert result["verified"] is False
        assert result["callback_id"] == 2
        assert any("not present on Bridge" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_add_failure_returns_none_id(self, client):
        """Bridge answers success:false → callback_id None, verified False."""
        with patch.object(client, "list_callbacks",
                          new_callable=AsyncMock, return_value=[]), \
             patch.object(client, "remove_callback",
                          new_callable=AsyncMock) as mock_rm, \
             patch.object(client, "_add_callback",
                          new_callable=AsyncMock, return_value=None):
            result = await client.reset_callbacks(CB_URL)

        mock_rm.assert_not_awaited()
        assert result["callback_id"] is None
        assert result["verified"] is False
        assert result["removed"] == []

    @pytest.mark.asyncio
    async def test_removal_loop_is_bounded(self, client, caplog):
        """If remove silently fails the loop stops at the bound, no hang."""
        stale = [{"id": 0, "url": "http://10.0.0.9:8080/nuki/callback"}]
        with patch.object(client, "list_callbacks",
                          new_callable=AsyncMock, return_value=stale), \
             patch.object(client, "remove_callback",
                          new_callable=AsyncMock, return_value=True) as mock_rm, \
             patch.object(client, "_add_callback",
                          new_callable=AsyncMock, return_value=None):
            with caplog.at_level(logging.WARNING, logger="nuki_client"):
                result = await client.reset_callbacks(CB_URL)

        assert mock_rm.await_count == 4
        assert result["removed"] == [0, 0, 0, 0]
        assert result["verified"] is False
        assert any("still present" in r.getMessage() for r in caplog.records)
