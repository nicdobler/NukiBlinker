"""Tests for nukiblinker.event_router — classification, person resolution, dispatch."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nukiblinker.config import AppConfig
from nukiblinker.event_router import (
    classify,
    correlate_opener_open,
    dispatch_with_actions,
    resolve_person,
)
from nukiblinker import event_router


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
        """Regression #97: Opener state==1 ('online') must NOT be a ring.

        #180: it is now surfaced as ``opener_status`` (for Nuki Web correlation)
        instead of a ring.
        """
        payload = {"deviceType": 2, "nukiId": 100, "state": 1, "ringactionState": False}
        assert classify(payload, AppConfig()) == "opener_status"

    def test_state_1_without_ringaction_is_opener_status(self):
        """#180: bare state==1 status callbacks become opener_status (was ignored)."""
        payload = {"deviceType": 2, "nukiId": 100, "state": 1}
        assert classify(payload, AppConfig()) == "opener_status"

    def test_ring_to_open_takes_priority_over_ringaction(self):
        payload = {
            "deviceType": 2, "nukiId": 100, "state": 7, "ringactionState": True,
        }
        assert classify(payload, AppConfig()) == "ring_to_open"

    def test_rto_active_state_3_is_opener_status(self):
        """#180: state==3 (rto active) status callback becomes opener_status."""
        payload = {"deviceType": 2, "nukiId": 100, "state": 3, "ringactionState": False}
        assert classify(payload, AppConfig()) == "opener_status"

    def test_opener_id_filter_match(self):
        cfg = AppConfig()
        cfg.nuki.opener_id = 100
        payload = {"deviceType": 2, "nukiId": 100, "state": 7}
        assert classify(payload, cfg) == "ring_to_open"

    def test_opener_id_filter_mismatch(self):
        """A non-matching opener is ignored entirely — not surfaced for correlation."""
        cfg = AppConfig()
        cfg.nuki.opener_id = 200
        payload = {"deviceType": 2, "nukiId": 100, "state": 7}
        assert classify(payload, cfg) is None

    def test_opener_id_filter_mismatch_status_callback(self):
        """#180: a status callback from a non-matching opener stays ignored (None)."""
        cfg = AppConfig()
        cfg.nuki.opener_id = 200
        payload = {"deviceType": 2, "nukiId": 100, "state": 1}
        assert classify(payload, cfg) is None


class TestClassifySmartLock:
    """Smart Lock events (deviceType=0)."""

    def test_unlocked_ignored(self):
        """Regression #60: unlocking without opening must NOT fire door_opened."""
        payload = {"deviceType": 0, "nukiId": 200, "state": 3}
        assert classify(payload, AppConfig()) is None

    def test_unlocked_with_door_sensor_opened(self):
        """Regression #169: doorsensorState=3 triggers door_opened even when state=3."""
        payload = {
            "deviceType": 0,
            "nukiId": 200,
            "state": 3,
            "stateName": "unlocked",
            "doorsensorState": 3,
            "doorsensorStateName": "door opened",
        }
        assert classify(payload, AppConfig()) == "door_opened"

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
    """Person name resolution via the Nuki Web API only (#175)."""

    @pytest.mark.asyncio
    async def test_no_web_client_uses_fallback(self):
        """#175: without a Web API client there is no name source — use fallback."""
        result = await resolve_person({"nukiId": 100})
        assert result == {"name": "Alguien", "name_source": "fallback"}

    @pytest.mark.asyncio
    async def test_custom_fallback_name(self):
        result = await resolve_person({"nukiId": 100}, "Desconocido")
        assert result == {"name": "Desconocido", "name_source": "fallback"}

    @pytest.mark.asyncio
    async def test_web_api_returns_name_and_trigger(self):
        """Without a web_id mapping, the global log (smartlock_id=None) is queried."""
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "name": "Nico", "trigger": 2, "source": 1},
        ]
        result = await resolve_person({"nukiId": 100}, nuki_web=web)
        assert result == {"name": "Nico", "trigger": 2, "name_source": "web_api"}
        web.get_recent_log.assert_awaited_once_with(smartlock_id=None, limit=20)

    @pytest.mark.asyncio
    async def test_web_api_uses_opener_web_id_not_bridge_id(self):
        """#190: when opener_web_id is configured, it is used — not the Bridge nukiId."""
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 9129696002, "name": "Nico", "trigger": 5, "source": 1},
        ]
        cfg = AppConfig()
        cfg.nuki.opener_web_id = 9129696002  # Web smartlockId (different from Bridge nukiId)
        result = await resolve_person(
            {"nukiId": 100, "deviceType": 2}, nuki_web=web, config=cfg,
        )
        assert result == {"name": "Nico", "trigger": 5, "name_source": "web_api"}
        web.get_recent_log.assert_awaited_once_with(smartlock_id=9129696002, limit=20)

    @pytest.mark.asyncio
    async def test_web_api_falls_back_to_global_log_when_no_web_id(self):
        """#190: when opener_web_id is None, smartlock_id=None (global log endpoint)."""
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 9129696002, "name": "Nico", "trigger": 5, "source": 1},
        ]
        cfg = AppConfig()  # opener_web_id defaults to None
        result = await resolve_person(
            {"nukiId": 100, "deviceType": 2}, nuki_web=web, config=cfg,
        )
        assert result["name"] == "Nico"
        web.get_recent_log.assert_awaited_once_with(smartlock_id=None, limit=20)

    @pytest.mark.asyncio
    async def test_web_api_named_entry_without_trigger_omits_trigger_key(self):
        """#145: a named Web API entry with no trigger omits the trigger key."""
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "name": "Nico", "trigger": None, "source": 1},
        ]
        result = await resolve_person({"nukiId": 100}, nuki_web=web)
        assert result == {"name": "Nico", "name_source": "web_api"}
        assert "trigger" not in result

    @pytest.mark.asyncio
    async def test_web_api_empty_uses_fallback(self):
        """#175: an empty Web log resolves to the fallback (no bridge retry)."""
        web = AsyncMock()
        web.get_recent_log.return_value = []
        result = await resolve_person({"nukiId": 100}, nuki_web=web)
        assert result == {"name": "Alguien", "name_source": "fallback"}

    @pytest.mark.asyncio
    async def test_web_api_exception_uses_fallback(self):
        """#175: a Web API failure resolves to the fallback (no bridge retry)."""
        web = AsyncMock()
        web.get_recent_log.side_effect = Exception("cloud down")
        result = await resolve_person({"nukiId": 100}, nuki_web=web)
        assert result == {"name": "Alguien", "name_source": "fallback"}

    @pytest.mark.asyncio
    async def test_web_api_unnamed_entry_surfaces_trigger_with_fallback(self):
        """#97: trigger is surfaced even when no name resolves."""
        web = AsyncMock()
        web.get_recent_log.return_value = [{"smartlockId": 100, "trigger": 2, "source": 1}]
        result = await resolve_person({"nukiId": 100}, nuki_web=web)
        assert result == {"name": "Alguien", "trigger": 2, "name_source": "fallback"}

    @pytest.mark.asyncio
    async def test_web_api_skips_door_sensor_entries_to_find_name(self):
        """#157: door-sensor entries (source=2) are skipped to find the real opener's name."""
        from nukiblinker.nuki_web_client import SOURCE_DOOR_SENSOR
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "trigger": 5, "source": SOURCE_DOOR_SENSOR},  # sensor, no name
            {"smartlockId": 100, "name": "Nico", "trigger": 2, "source": 1},   # real opener
        ]
        result = await resolve_person({"nukiId": 100}, nuki_web=web)
        assert result["name"] == "Nico"
        assert result["name_source"] == "web_api"

    @pytest.mark.asyncio
    async def test_web_api_anonymous_non_sensor_entry_does_not_look_further(self):
        """#157/#155: first non-sensor entry with no name → anonymous, don't look further."""
        from nukiblinker.nuki_web_client import SOURCE_DOOR_SENSOR
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "trigger": 5, "source": SOURCE_DOOR_SENSOR},   # sensor, skip
            {"smartlockId": 100, "trigger": 6, "source": 1},                    # non-sensor, anonymous RTO
            {"smartlockId": 100, "name": "Nico", "trigger": 2, "source": 1},    # older — must NOT be used
        ]
        result = await resolve_person({"nukiId": 100}, nuki_web=web)
        assert result["name_source"] == "fallback"
        assert result.get("name") != "Nico"

    @pytest.mark.asyncio
    async def test_web_api_does_not_use_stale_name_from_older_entry(self):
        """#155: only the MOST RECENT entry is trusted.

        A fresh anonymous Ring-to-Open (most recent entry has no name) must NOT
        inherit a stale name from an older named entry. It falls through to the
        fallback, while still surfacing the most-recent trigger.
        """
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "trigger": 6, "source": 1},          # most recent: anonymous RTO
            {"smartlockId": 100, "name": "Nico", "trigger": 2},       # older: stale named open
        ]
        result = await resolve_person({"nukiId": 100}, nuki_web=web)
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


# ---------------------------------------------------------------------------
# dispatch_with_actions() — which events resolve a name (#175/#176/#177)
# ---------------------------------------------------------------------------


class TestDispatchResolutionSet:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("event_type", ["ring", "ring_to_open"])
    async def test_opener_events_resolve_name(self, monkeypatch, event_type):
        """#177: ring and ring_to_open resolve the caller's name via Nuki Web."""
        resolver = AsyncMock(return_value={"name": "Nico", "name_source": "web_api"})
        monkeypatch.setattr("nukiblinker.event_router.resolve_person", resolver)
        monkeypatch.setattr(
            "nukiblinker.notifier.notify_with_actions",
            AsyncMock(return_value=[]),
        )
        cfg = AppConfig()
        rule = getattr(cfg.events, event_type)
        await dispatch_with_actions(event_type, {"nukiId": 100}, cfg, object(), rule)
        resolver.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_door_opened_does_not_resolve_name(self, monkeypatch):
        """#176: door_opened (Lock) must NOT resolve a name — chime/blink only."""
        resolver = AsyncMock(return_value={"name": "Nico", "name_source": "web_api"})
        monkeypatch.setattr("nukiblinker.event_router.resolve_person", resolver)
        notify = AsyncMock(return_value=[])
        monkeypatch.setattr("nukiblinker.notifier.notify_with_actions", notify)
        cfg = AppConfig()
        await dispatch_with_actions(
            "door_opened", {"nukiId": 200}, cfg, object(), cfg.events.door_opened,
        )
        resolver.assert_not_called()
        # Context passed to the notifier is empty (no name).
        assert notify.await_args.args[3] == {}


# ---------------------------------------------------------------------------
# correlate_opener_open() — #180
# ---------------------------------------------------------------------------


class _Clock:
    """Deterministic monotonic clock returning a preset sequence."""

    def __init__(self, values):
        self._values = list(values)
        self.i = 0

    def __call__(self):
        v = self._values[min(self.i, len(self._values) - 1)]
        self.i += 1
        return v


_FIXED_NOW = datetime(2026, 6, 17, 16, 15, 0, tzinfo=timezone.utc)


class TestCorrelateOpenerOpen:
    @pytest.fixture(autouse=True)
    def _reset_guard(self):
        event_router._correlation_block_until.clear()
        yield
        event_router._correlation_block_until.clear()

    def _clients(self, web):
        return SimpleNamespace(nuki_web=web)

    @pytest.mark.asyncio
    async def test_hit_on_first_poll_returns_context(self):
        """#190: without a web_id mapping, the global log (smartlock_id=None) is used."""
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 9129696002, "name": "Nico", "trigger": 5, "source": 1,
             "date": _FIXED_NOW.isoformat()},
        ]
        cfg = AppConfig()
        result = await correlate_opener_open(
            {"nukiId": 100}, cfg, self._clients(web),
            sleep=AsyncMock(), time_func=_Clock([0, 0]), now_func=lambda: _FIXED_NOW,
        )
        assert result == {"name": "Nico", "trigger": 5, "name_source": "web_api"}
        web.get_recent_log.assert_awaited_once_with(smartlock_id=None, limit=20)

    @pytest.mark.asyncio
    async def test_correlate_uses_opener_web_id_not_bridge_id(self):
        """#190: correlate_opener_open uses opener_web_id when set, not Bridge nukiId."""
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 9129696002, "name": "Nico", "trigger": 5, "source": 1,
             "date": _FIXED_NOW.isoformat()},
        ]
        cfg = AppConfig()
        cfg.nuki.opener_web_id = 9129696002
        result = await correlate_opener_open(
            {"nukiId": 100, "deviceType": 2}, cfg, self._clients(web),
            sleep=AsyncMock(), time_func=_Clock([0, 0]), now_func=lambda: _FIXED_NOW,
        )
        assert result is not None
        assert result["name"] == "Nico"
        web.get_recent_log.assert_awaited_once_with(smartlock_id=9129696002, limit=20)

    @pytest.mark.asyncio
    async def test_no_web_client_returns_none(self):
        result = await correlate_opener_open(
            {"nukiId": 100}, AppConfig(), SimpleNamespace(nuki_web=None),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_disabled_returns_none(self):
        web = AsyncMock()
        cfg = AppConfig()
        cfg.opener_correlation.enabled = False
        result = await correlate_opener_open({"nukiId": 100}, cfg, self._clients(web))
        assert result is None
        web.get_recent_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_user_open_polls_then_returns_none(self):
        web = AsyncMock()
        web.get_recent_log.return_value = []  # nothing to correlate
        sleep = AsyncMock()
        cfg = AppConfig()
        result = await correlate_opener_open(
            {"nukiId": 100}, cfg, self._clients(web),
            sleep=sleep, time_func=_Clock([0, 6, 12]), now_func=lambda: _FIXED_NOW,
        )
        assert result is None
        assert web.get_recent_log.await_count == 2  # polled twice within the window
        sleep.assert_awaited()

    @pytest.mark.asyncio
    async def test_stale_open_outside_recency_is_ignored(self):
        from datetime import timedelta
        old_date = (_FIXED_NOW - timedelta(seconds=600)).isoformat()
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "name": "Nico", "trigger": 5, "source": 1, "date": old_date},
        ]
        cfg = AppConfig()
        result = await correlate_opener_open(
            {"nukiId": 100}, cfg, self._clients(web),
            sleep=AsyncMock(), time_func=_Clock([0, 6, 12]), now_func=lambda: _FIXED_NOW,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_cooldown_guard_skips_overlapping_run(self):
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "name": "Nico", "trigger": 5, "source": 1,
             "date": _FIXED_NOW.isoformat()},
        ]
        cfg = AppConfig()
        # First call hits and sets a cooldown.
        first = await correlate_opener_open(
            {"nukiId": 100}, cfg, self._clients(web),
            sleep=AsyncMock(), time_func=_Clock([0, 0]), now_func=lambda: _FIXED_NOW,
        )
        assert first is not None
        web.get_recent_log.reset_mock()
        # Second call within the cooldown window is skipped (no polling).
        second = await correlate_opener_open(
            {"nukiId": 100}, cfg, self._clients(web),
            sleep=AsyncMock(), time_func=_Clock([1, 1]), now_func=lambda: _FIXED_NOW,
        )
        assert second is None
        web.get_recent_log.assert_not_called()
