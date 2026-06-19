"""Tests for nukiblinker.event_router — classification, person resolution, dispatch."""

from unittest.mock import AsyncMock

import pytest

from nukiblinker.config import AppConfig
from nukiblinker.event_router import (
    classify,
    dispatch_with_actions,
    resolve_person,
)


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

        #197: it is now ignored (returns None) — the bridge always fires state=7
        ("opening") for actual opens; state=1 is only a post-open idle callback.
        """
        payload = {"deviceType": 2, "nukiId": 100, "state": 1, "ringactionState": False}
        assert classify(payload, AppConfig()) is None

    def test_state_1_without_ringaction_is_ignored(self):
        """#197: bare state==1 status callbacks are now ignored (not opener_status)."""
        payload = {"deviceType": 2, "nukiId": 100, "state": 1}
        assert classify(payload, AppConfig()) is None

    def test_ring_to_open_takes_priority_over_ringaction(self):
        payload = {
            "deviceType": 2, "nukiId": 100, "state": 7, "ringactionState": True,
        }
        assert classify(payload, AppConfig()) == "ring_to_open"

    def test_rto_active_state_3_is_ignored(self):
        """#197: state==3 (rto active) is now ignored — not a user-driven open."""
        payload = {"deviceType": 2, "nukiId": 100, "state": 3, "ringactionState": False}
        assert classify(payload, AppConfig()) is None

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

    def test_opener_status_callback_non_matching_opener_ignored(self):
        """A status callback from a non-matching opener stays ignored (None)."""
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

    @pytest.mark.asyncio
    async def test_entry_25s_old_retried_for_fresh_name(self):
        """#197: an entry 25s before ring_ts was accepted by the old 30s threshold
        but is now stale under the tighter 10s threshold — must retry and resolve
        the correct name ('Ele') instead of immediately returning 'Nico'.
        """
        slept = []

        async def fake_sleep(s):
            slept.append(s)

        ring_ts = "2026-06-19T15:25:00+00:00"
        # First call: "Nico" from 25 seconds before ring — was accepted before, now stale.
        nico_entry = [{"smartlockId": 9129696002, "name": "Nico", "trigger": 5, "source": 1,
                       "date": "2026-06-19T15:24:35+00:00"}]
        # Second call: "Ele" right at the ring time — fresh.
        ele_entry = [{"smartlockId": 9129696002, "name": "Ele", "trigger": 5, "source": 1,
                      "date": "2026-06-19T15:25:00+00:00"}]
        web = AsyncMock()
        web.get_recent_log.side_effect = [nico_entry, ele_entry]
        payload = {"nukiId": 539761410, "ringactionTimestamp": ring_ts}
        result = await resolve_person(payload, nuki_web=web, sleep=fake_sleep)
        assert result["name"] == "Ele"
        assert result["name_source"] == "web_api"
        assert web.get_recent_log.await_count == 2
        assert len(slept) == 1

    @pytest.mark.asyncio
    async def test_stale_candidate_retried_until_fresh_entry_arrives(self):
        """#193: when the Web API lags, resolve_person retries until a fresh entry appears.

        First call returns a 42-minute-old 'Celi' entry (stale relative to the
        ring timestamp). Second call returns the actual 'Nico' entry at the ring time.
        """
        slept = []

        async def fake_sleep(s):
            slept.append(s)

        ring_ts = "2026-06-19T09:01:27+00:00"
        web = AsyncMock()
        web.get_recent_log.side_effect = [
            # Attempt 0: Celi from 42 min ago — stale
            [{"smartlockId": 9129696002, "name": "Celi", "trigger": 0, "source": 0,
              "date": "2026-06-19T08:19:55.000Z"}],
            # Attempt 1: Nico at the ring time — fresh
            [{"smartlockId": 9129696002, "name": "Nico", "trigger": 0, "source": 0,
              "date": "2026-06-19T09:01:27.000Z"}],
        ]
        payload = {"nukiId": 539761410, "ringactionTimestamp": ring_ts}
        result = await resolve_person(payload, nuki_web=web, sleep=fake_sleep)
        assert result["name"] == "Nico"
        assert result["name_source"] == "web_api"
        assert web.get_recent_log.await_count == 2
        assert len(slept) == 1  # exactly one retry delay

    @pytest.mark.asyncio
    async def test_stale_candidate_falls_back_after_max_retries(self):
        """#193: if the Web API never delivers a fresh entry, fall back after max retries."""
        from nukiblinker import event_router as er

        slept = []

        async def fake_sleep(s):
            slept.append(s)

        ring_ts = "2026-06-19T09:01:27+00:00"
        stale_entry = [{"smartlockId": 9129696002, "name": "Celi", "trigger": 0,
                        "source": 0, "date": "2026-06-19T08:19:55.000Z"}]
        web = AsyncMock()
        web.get_recent_log.return_value = stale_entry  # always stale
        payload = {"nukiId": 539761410, "ringactionTimestamp": ring_ts}
        result = await resolve_person(payload, nuki_web=web, sleep=fake_sleep)
        assert result["name_source"] == "fallback"
        assert web.get_recent_log.await_count == er._RESOLVE_MAX_RETRIES + 1
        assert len(slept) == er._RESOLVE_MAX_RETRIES

    @pytest.mark.asyncio
    async def test_no_ring_ts_in_payload_skips_recency_check(self):
        """#193: when ringactionTimestamp is absent, no retry is done (no ts to compare)."""
        slept = []

        async def fake_sleep(s):
            slept.append(s)

        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "name": "Celi", "trigger": 0, "source": 0,
             "date": "2026-06-19T08:19:55.000Z"},
        ]
        # Payload has no ringactionTimestamp — recency check must be skipped
        result = await resolve_person({"nukiId": 100}, nuki_web=web, sleep=fake_sleep)
        assert result["name"] == "Celi"
        assert result["name_source"] == "web_api"
        assert len(slept) == 0  # no retries
        assert web.get_recent_log.await_count == 1


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
