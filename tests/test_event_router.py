"""Tests for nukiblinker.event_router — classification, person resolution, dispatch."""

from unittest.mock import AsyncMock

import pytest

from nukiblinker.config import AppConfig
from nukiblinker.event_router import classify, dispatch_with_actions, resolve_person


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

    def test_unlatching_state_7(self):
        """Regression #160: state 7 (unlatching) must also trigger door_opened."""
        payload = {"deviceType": 0, "nukiId": 200, "state": 7}
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
        assert result == {"name": "Nico", "name_source": "bridge_log"}
        nuki.get_last_log.assert_called_once_with(100)

    @pytest.mark.asyncio
    async def test_fallback_on_empty_name(self):
        nuki = AsyncMock()
        nuki.get_last_log.return_value = {"name": "", "action": 3}
        result = await resolve_person({"nukiId": 100}, nuki)
        assert result == {"name": "Alguien", "name_source": "fallback"}

    @pytest.mark.asyncio
    async def test_retries_until_log_has_name(self):
        """Regression #60: bridge log lags behind the callback — retry resolves the name."""
        nuki = AsyncMock()
        nuki.get_last_log.side_effect = [None, {"name": "Elena", "action": 6}]
        result = await resolve_person({"nukiId": 100}, nuki)
        assert result == {"name": "Elena", "name_source": "bridge_log"}
        assert nuki.get_last_log.call_count == 2

    @pytest.mark.asyncio
    async def test_fallback_on_exception(self):
        nuki = AsyncMock()
        nuki.get_last_log.side_effect = Exception("network error")
        result = await resolve_person({"nukiId": 100}, nuki)
        assert result == {"name": "Alguien", "name_source": "fallback"}

    @pytest.mark.asyncio
    async def test_fallback_on_none_client(self):
        result = await resolve_person({"nukiId": 100}, None)
        assert result == {"name": "Alguien", "name_source": "fallback"}

    @pytest.mark.asyncio
    async def test_fallback_on_missing_nuki_id(self):
        nuki = AsyncMock()
        result = await resolve_person({}, nuki)
        assert result == {"name": "Alguien", "name_source": "fallback"}

    @pytest.mark.asyncio
    async def test_custom_fallback_name(self):
        nuki = AsyncMock()
        nuki.get_last_log.side_effect = Exception("fail")
        result = await resolve_person({"nukiId": 100}, nuki, fallback_name="Desconocido")
        assert result == {"name": "Desconocido", "name_source": "fallback"}

    @pytest.mark.asyncio
    async def test_web_api_preferred_returns_name_and_trigger(self):
        """When a Web API client is provided, it is used and returns name + trigger."""
        nuki = AsyncMock()
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "name": "Nico", "trigger": 2, "source": 1},
        ]
        result = await resolve_person({"nukiId": 100}, nuki, nuki_web=web)
        assert result == {"name": "Nico", "trigger": 2, "name_source": "web_api"}
        web.get_recent_log.assert_awaited_once_with(smartlock_id=100, limit=20)
        nuki.get_last_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_web_api_named_entry_without_trigger_omits_trigger_key(self):
        """#145: a named Web API entry with no trigger omits the trigger key.

        Both resolution paths must produce a consistent context dict: the
        ``trigger`` key is present only when known, never as an explicit None.
        """
        nuki = AsyncMock()
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "name": "Nico", "trigger": None, "source": 1},
        ]
        result = await resolve_person({"nukiId": 100}, nuki, nuki_web=web)
        assert result == {"name": "Nico", "name_source": "web_api"}
        assert "trigger" not in result
        nuki.get_last_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_web_api_empty_falls_back_to_bridge_log(self):
        nuki = AsyncMock()
        nuki.get_last_log.return_value = {"name": "Elena"}
        web = AsyncMock()
        web.get_recent_log.return_value = []
        result = await resolve_person({"nukiId": 100}, nuki, nuki_web=web)
        assert result == {"name": "Elena", "name_source": "bridge_log"}
        nuki.get_last_log.assert_called_once_with(100)

    @pytest.mark.asyncio
    async def test_web_api_exception_falls_back_to_bridge_log(self):
        nuki = AsyncMock()
        nuki.get_last_log.return_value = {"name": "Elena"}
        web = AsyncMock()
        web.get_recent_log.side_effect = Exception("cloud down")
        result = await resolve_person({"nukiId": 100}, nuki, nuki_web=web)
        assert result == {"name": "Elena", "name_source": "bridge_log"}

    @pytest.mark.asyncio
    async def test_web_api_unnamed_entry_surfaces_trigger_with_bridge_name(self):
        """#97: an anonymous open still surfaces the trigger for the user to confirm."""
        nuki = AsyncMock()
        nuki.get_last_log.return_value = {"name": "Elena"}
        web = AsyncMock()
        web.get_recent_log.return_value = [{"smartlockId": 100, "trigger": 2, "source": 1}]
        result = await resolve_person({"nukiId": 100}, nuki, nuki_web=web)
        assert result == {"name": "Elena", "trigger": 2, "name_source": "bridge_log"}

    @pytest.mark.asyncio
    async def test_web_api_unnamed_entry_surfaces_trigger_with_fallback(self):
        """#97: trigger is surfaced even when no name resolves anywhere."""
        nuki = AsyncMock()
        nuki.get_last_log.return_value = {"name": ""}
        web = AsyncMock()
        web.get_recent_log.return_value = [{"smartlockId": 100, "trigger": 2}]
        result = await resolve_person({"nukiId": 100}, nuki, nuki_web=web)
        assert result == {"name": "Alguien", "trigger": 2, "name_source": "fallback"}

    @pytest.mark.asyncio
    async def test_web_api_skips_door_sensor_entries_to_find_name(self):
        """#157: door-sensor entries (source=2) are skipped to find the real opener's name."""
        from nukiblinker.nuki_web_client import SOURCE_DOOR_SENSOR
        nuki = AsyncMock()
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "trigger": 5, "source": SOURCE_DOOR_SENSOR},  # sensor, no name
            {"smartlockId": 100, "name": "Nico", "trigger": 2, "source": 1},   # real opener
        ]
        result = await resolve_person({"nukiId": 100}, nuki, nuki_web=web)
        assert result["name"] == "Nico"
        assert result["name_source"] == "web_api"
        nuki.get_last_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_web_api_anonymous_non_sensor_entry_does_not_look_further(self):
        """#157/#155: first non-sensor entry with no name → anonymous, don't look further."""
        from nukiblinker.nuki_web_client import SOURCE_DOOR_SENSOR
        nuki = AsyncMock()
        nuki.get_last_log.return_value = {"name": ""}
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "trigger": 5, "source": SOURCE_DOOR_SENSOR},   # sensor, skip
            {"smartlockId": 100, "trigger": 6, "source": 1},                    # non-sensor, anonymous RTO
            {"smartlockId": 100, "name": "Nico", "trigger": 2, "source": 1},    # older — must NOT be used
        ]
        result = await resolve_person({"nukiId": 100}, nuki, nuki_web=web)
        assert result["name_source"] == "fallback"
        assert result.get("name") != "Nico"

    @pytest.mark.asyncio
    async def test_web_api_does_not_use_stale_name_from_older_entry(self):
        """#155: only the MOST RECENT entry is trusted.

        A fresh anonymous Ring-to-Open (most recent entry has no name) must NOT
        inherit a stale name from an older named entry. It falls through to the
        bridge log / fallback, while still surfacing the most-recent trigger.
        """
        nuki = AsyncMock()
        nuki.get_last_log.return_value = {"name": ""}  # bridge has no name either
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "trigger": 6, "source": 1},          # most recent: anonymous RTO
            {"smartlockId": 100, "name": "Nico", "trigger": 2},       # older: stale named open
        ]
        result = await resolve_person({"nukiId": 100}, nuki, nuki_web=web)
        assert result == {"name": "Alguien", "trigger": 6, "name_source": "fallback"}
        assert "Nico" not in result.values()


# ---------------------------------------------------------------------------
# dispatch_with_actions() — trigger observability (#97)
# ---------------------------------------------------------------------------


class TestDispatchTriggerObservability:
    @pytest.mark.asyncio
    async def test_trigger_surfaced_in_actions(self, monkeypatch):
        """#97: resolved trigger is prepended to the Event Log actions."""
        monkeypatch.setattr(
            "nukiblinker.event_router.resolve_person",
            AsyncMock(return_value={"name": "Alguien", "trigger": 2}),
        )
        monkeypatch.setattr(
            "nukiblinker.notifier.notify_with_actions",
            AsyncMock(return_value=["Hue lights blinked"]),
        )
        cfg = AppConfig()
        rule = cfg.events.ring_to_open
        actions = await dispatch_with_actions(
            "ring_to_open", {"nukiId": 100}, cfg, object(), rule,
        )
        assert actions[0] == "Trigger: button (2)"
        assert "Hue lights blinked" in actions

    @pytest.mark.asyncio
    async def test_anonymous_name_surfaced_in_actions(self, monkeypatch):
        """#155: a fallback (anonymous) resolution is flagged in the Event Log."""
        monkeypatch.setattr(
            "nukiblinker.event_router.resolve_person",
            AsyncMock(return_value={"name": "Alguien", "name_source": "fallback"}),
        )
        monkeypatch.setattr(
            "nukiblinker.notifier.notify_with_actions",
            AsyncMock(return_value=["Hue lights blinked"]),
        )
        cfg = AppConfig()
        actions = await dispatch_with_actions(
            "ring_to_open", {"nukiId": 100}, cfg, object(), cfg.events.ring_to_open,
        )
        assert "Name: anonymous (no identity resolved)" in actions
        assert "Hue lights blinked" in actions

    @pytest.mark.asyncio
    async def test_resolved_name_not_flagged_anonymous(self, monkeypatch):
        """#155: a real resolved name must NOT be flagged as anonymous."""
        monkeypatch.setattr(
            "nukiblinker.event_router.resolve_person",
            AsyncMock(return_value={"name": "Nico", "name_source": "web_api"}),
        )
        monkeypatch.setattr(
            "nukiblinker.notifier.notify_with_actions",
            AsyncMock(return_value=["Hue lights blinked"]),
        )
        cfg = AppConfig()
        actions = await dispatch_with_actions(
            "ring_to_open", {"nukiId": 100}, cfg, object(), cfg.events.ring_to_open,
        )
        assert not any("anonymous" in a for a in actions)

    @pytest.mark.asyncio
    async def test_no_trigger_means_no_trigger_action(self, monkeypatch):
        monkeypatch.setattr(
            "nukiblinker.event_router.resolve_person",
            AsyncMock(return_value={"name": "Alguien"}),
        )
        monkeypatch.setattr(
            "nukiblinker.notifier.notify_with_actions",
            AsyncMock(return_value=["Hue lights blinked"]),
        )
        cfg = AppConfig()
        actions = await dispatch_with_actions(
            "ring_to_open", {"nukiId": 100}, cfg, object(), cfg.events.ring_to_open,
        )
        assert not any(a.startswith("Trigger:") for a in actions)
