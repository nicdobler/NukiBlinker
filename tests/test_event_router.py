"""Tests for nukiblinker.event_router — classification, person resolution, dispatch."""

from unittest.mock import AsyncMock

import pytest

from nukiblinker.config import AppConfig
from nukiblinker.event_router import classify, resolve_person


# ---------------------------------------------------------------------------
# classify()
# ---------------------------------------------------------------------------


class TestClassifyOpener:
    """Opener events (deviceType=2)."""

    def test_ring_to_open(self):
        payload = {"deviceType": 2, "nukiId": 100, "state": 7}
        assert classify(payload, AppConfig()) == "ring_to_open"

    def test_ring_via_ringaction_state(self):
        """#97: a ring is signalled by ringactionState, not by state."""
        payload = {
            "deviceType": 2, "nukiId": 100, "state": 1,
            "ringactionState": True,
            "ringactionTimestamp": "2026-06-12T13:51:05+00:00",
        }
        assert classify(payload, AppConfig()) == "ring"

    def test_state_1_online_is_not_ring(self):
        """Regression #97: Opener state==1 ('online') must NOT be a ring."""
        payload = {"deviceType": 2, "nukiId": 100, "state": 1, "ringactionState": False}
        assert classify(payload, AppConfig()) is None

    def test_state_1_without_ringaction_is_ignored(self):
        """Regression #97: bare state==1 status callbacks are ignored."""
        payload = {"deviceType": 2, "nukiId": 100, "state": 1}
        assert classify(payload, AppConfig()) is None

    def test_ring_to_open_takes_priority_over_ringaction(self):
        payload = {
            "deviceType": 2, "nukiId": 100, "state": 7, "ringactionState": True,
        }
        assert classify(payload, AppConfig()) == "ring_to_open"

    def test_ignored_state(self):
        payload = {"deviceType": 2, "nukiId": 100, "state": 3}
        assert classify(payload, AppConfig()) is None

    def test_opener_id_filter_match(self):
        cfg = AppConfig()
        cfg.nuki.opener_id = 100
        payload = {"deviceType": 2, "nukiId": 100, "state": 7}
        assert classify(payload, cfg) == "ring_to_open"

    def test_opener_id_filter_mismatch(self):
        cfg = AppConfig()
        cfg.nuki.opener_id = 200
        payload = {"deviceType": 2, "nukiId": 100, "state": 7}
        assert classify(payload, cfg) is None


class TestClassifySmartLock:
    """Smart Lock events (deviceType=0)."""

    def test_unlocked_ignored(self):
        """Regression #60: unlocking without opening must NOT fire door_opened."""
        payload = {"deviceType": 0, "nukiId": 200, "state": 3}
        assert classify(payload, AppConfig()) is None

    def test_unlatched(self):
        payload = {"deviceType": 0, "nukiId": 200, "state": 5}
        assert classify(payload, AppConfig()) == "door_opened"

    def test_locked_ignored(self):
        payload = {"deviceType": 0, "nukiId": 200, "state": 1}
        assert classify(payload, AppConfig()) is None

    def test_lock_id_filter_match(self):
        cfg = AppConfig()
        cfg.nuki.lock_id = 200
        payload = {"deviceType": 0, "nukiId": 200, "state": 5}
        assert classify(payload, cfg) == "door_opened"

    def test_lock_id_filter_mismatch(self):
        cfg = AppConfig()
        cfg.nuki.lock_id = 300
        payload = {"deviceType": 0, "nukiId": 200, "state": 5}
        assert classify(payload, cfg) is None


class TestClassifyOther:
    """Unknown or missing deviceType."""

    def test_unknown_device_type(self):
        payload = {"deviceType": 99, "nukiId": 1, "state": 1}
        assert classify(payload, AppConfig()) is None

    def test_missing_device_type(self):
        payload = {"nukiId": 1, "state": 1}
        assert classify(payload, AppConfig()) is None


# ---------------------------------------------------------------------------
# resolve_person()
# ---------------------------------------------------------------------------


class TestResolvePerson:
    """Person name resolution from Nuki /log endpoint."""

    @pytest.fixture(autouse=True)
    def _no_retry_delay(self, monkeypatch):
        monkeypatch.setattr("nukiblinker.event_router._RESOLVE_PERSON_RETRY_SECONDS", 0)

    @pytest.mark.asyncio
    async def test_resolves_name_from_log(self):
        nuki = AsyncMock()
        nuki.get_last_log.return_value = {"name": "Nico", "action": 3}
        payload = {"nukiId": 100}
        result = await resolve_person(payload, nuki)
        assert result == {"name": "Nico"}
        nuki.get_last_log.assert_called_once_with(100)

    @pytest.mark.asyncio
    async def test_fallback_on_empty_name(self):
        nuki = AsyncMock()
        nuki.get_last_log.return_value = {"name": "", "action": 3}
        result = await resolve_person({"nukiId": 100}, nuki)
        assert result == {"name": "Alguien"}

    @pytest.mark.asyncio
    async def test_retries_until_log_has_name(self):
        """Regression #60: bridge log lags behind the callback — retry resolves the name."""
        nuki = AsyncMock()
        nuki.get_last_log.side_effect = [None, {"name": "Elena", "action": 6}]
        result = await resolve_person({"nukiId": 100}, nuki)
        assert result == {"name": "Elena"}
        assert nuki.get_last_log.call_count == 2

    @pytest.mark.asyncio
    async def test_fallback_on_exception(self):
        nuki = AsyncMock()
        nuki.get_last_log.side_effect = Exception("network error")
        result = await resolve_person({"nukiId": 100}, nuki)
        assert result == {"name": "Alguien"}

    @pytest.mark.asyncio
    async def test_fallback_on_none_client(self):
        result = await resolve_person({"nukiId": 100}, None)
        assert result == {"name": "Alguien"}

    @pytest.mark.asyncio
    async def test_fallback_on_missing_nuki_id(self):
        nuki = AsyncMock()
        result = await resolve_person({}, nuki)
        assert result == {"name": "Alguien"}

    @pytest.mark.asyncio
    async def test_custom_fallback_name(self):
        nuki = AsyncMock()
        nuki.get_last_log.side_effect = Exception("fail")
        result = await resolve_person({"nukiId": 100}, nuki, fallback_name="Desconocido")
        assert result == {"name": "Desconocido"}

    @pytest.mark.asyncio
    async def test_web_api_preferred_returns_name_and_trigger(self):
        """When a Web API client is provided, it is used and returns name + trigger."""
        nuki = AsyncMock()
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "name": "Nico", "trigger": 2, "source": 1},
        ]
        result = await resolve_person({"nukiId": 100}, nuki, nuki_web=web)
        assert result == {"name": "Nico", "trigger": 2}
        web.get_recent_log.assert_awaited_once_with(smartlock_id=100, limit=20)
        nuki.get_last_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_web_api_empty_falls_back_to_bridge_log(self):
        nuki = AsyncMock()
        nuki.get_last_log.return_value = {"name": "Elena"}
        web = AsyncMock()
        web.get_recent_log.return_value = []
        result = await resolve_person({"nukiId": 100}, nuki, nuki_web=web)
        assert result == {"name": "Elena"}
        nuki.get_last_log.assert_called_once_with(100)

    @pytest.mark.asyncio
    async def test_web_api_exception_falls_back_to_bridge_log(self):
        nuki = AsyncMock()
        nuki.get_last_log.return_value = {"name": "Elena"}
        web = AsyncMock()
        web.get_recent_log.side_effect = Exception("cloud down")
        result = await resolve_person({"nukiId": 100}, nuki, nuki_web=web)
        assert result == {"name": "Elena"}
