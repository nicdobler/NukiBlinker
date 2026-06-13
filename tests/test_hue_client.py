"""Tests for nukiblinker.hue_client — mock httpx."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nukiblinker.hue_client import HueClient
from nukiblinker.config import CustomBlinkConfig


@pytest.fixture
def client():
    return HueClient("10.0.0.2", "test-key")


def _mock_response(json_data=None, status_code=200):
    resp = MagicMock()
    resp.json.return_value = json_data or {}
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


def _mock_http_client(**kwargs):
    mock_http = MagicMock()
    for method, responses in kwargs.items():
        if isinstance(responses, list):
            setattr(mock_http, method, AsyncMock(side_effect=responses))
        else:
            setattr(mock_http, method, AsyncMock(return_value=responses))
    return mock_http


def _patch_httpx(mock_http):
    ctx = patch("httpx.AsyncClient")
    mock_cls = ctx.start()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestTriggerAlert:
    @pytest.mark.asyncio
    async def test_sends_alert_to_lights_and_groups(self, client):
        resp = _mock_response([{"success": True}])
        mock_http = _mock_http_client(put=resp)
        ctx = _patch_httpx(mock_http)
        try:
            await client.trigger_alert([1, 2], [3])
            assert mock_http.put.call_count == 3
        finally:
            ctx.stop()


class TestCustomBlink:
    @pytest.mark.asyncio
    async def test_blink_saves_and_restores(self, client):
        saved_state = {"on": True, "bri": 200, "hue": 100, "sat": 50}
        get_resp = _mock_response({"state": saved_state})
        put_resp = _mock_response([{"success": True}])

        mock_http = _mock_http_client(get=get_resp, put=put_resp)
        ctx = _patch_httpx(mock_http)
        try:
            blink = CustomBlinkConfig(hue=0, saturation=254, brightness=254, flashes=1, interval_ms=10)
            await client.trigger_custom_blink([1], [2], blink)  # light_ids=[1], group_ids=[2]
            # get: 1 (save) | put: 2 (on, off) + 1 (restore) = 3
            assert mock_http.get.call_count == 1
            assert mock_http.put.call_count >= 3
        finally:
            ctx.stop()

    @pytest.mark.asyncio
    async def test_restore_preserves_color_temperature_mode(self, client):
        """Regression: a light in ct mode must be restored with ct, not hue/sat."""
        saved_state = {"on": True, "bri": 200, "ct": 366, "colormode": "ct",
                       "hue": 8000, "sat": 120}
        get_resp = _mock_response({"state": saved_state})
        put_resp = _mock_response([{"success": True}])

        mock_http = _mock_http_client(get=get_resp, put=put_resp)
        ctx = _patch_httpx(mock_http)
        try:
            blink = CustomBlinkConfig(hue=0, saturation=254, brightness=254, flashes=1, interval_ms=10)
            await client.trigger_custom_blink([1], [], blink)
            # The final PUT is the restore call.
            restore_body = mock_http.put.call_args_list[-1].kwargs["json"]
            assert restore_body["ct"] == 366
            assert "hue" not in restore_body
            assert "sat" not in restore_body
        finally:
            ctx.stop()


class TestListLights:
    @pytest.mark.asyncio
    async def test_returns_lights(self, client):
        lights = {"1": {"name": "Lamp"}, "2": {"name": "Ceiling"}}
        mock_http = _mock_http_client(get=_mock_response(lights))
        ctx = _patch_httpx(mock_http)
        try:
            result = await client.list_lights()
            assert "1" in result
        finally:
            ctx.stop()


class TestListGroups:
    @pytest.mark.asyncio
    async def test_returns_groups(self, client):
        groups = {"1": {"name": "Living room"}}
        mock_http = _mock_http_client(get=_mock_response(groups))
        ctx = _patch_httpx(mock_http)
        try:
            result = await client.list_groups()
            assert "1" in result
        finally:
            ctx.stop()


class TestPair:
    @pytest.mark.asyncio
    async def test_pairing_success(self):
        resp = _mock_response([{"success": {"username": "new-api-key"}}])
        mock_http = _mock_http_client(post=resp)
        ctx = _patch_httpx(mock_http)
        try:
            key = await HueClient.pair("10.0.0.2")
            assert key == "new-api-key"
        finally:
            ctx.stop()

    @pytest.mark.asyncio
    async def test_pairing_error_returns_none(self):
        resp = _mock_response([{"error": {"type": 101, "description": "link button not pressed"}}])
        mock_http = _mock_http_client(post=resp)
        ctx = _patch_httpx(mock_http)
        try:
            key = await HueClient.pair("10.0.0.2")
            assert key is None
        finally:
            ctx.stop()
