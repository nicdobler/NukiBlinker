"""Tests for nukiblinker.event_router — classification, person resolution, dispatch."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from nukiblinker.config import AppConfig
from nukiblinker.event_router import (
    RINGACTION_STALE_THRESHOLD_S,
    classify,
    classify_app_open_with_web,
    classify_state7_with_web,
    dispatch_with_actions,
    event_time_for_log,
    is_opener_app_open_candidate,
    is_opener_state7_candidate,
    resolve_person,
    ringaction_staleness,
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


class TestIsOpenerAppOpenCandidate:
    """#219 gate: state=1 online or state=3 rto-active (not a ring/state=7)."""

    def test_state1_is_candidate(self):
        payload = {"deviceType": 2, "nukiId": 100, "state": 1, "ringactionState": False}
        assert is_opener_app_open_candidate(payload, AppConfig()) is True

    def test_state3_is_candidate(self):
        payload = {"deviceType": 2, "nukiId": 100, "state": 3, "ringactionState": False}
        assert is_opener_app_open_candidate(payload, AppConfig()) is True

    def test_ring_is_not_candidate(self):
        payload = {"deviceType": 2, "nukiId": 100, "state": 1, "ringactionState": True}
        assert is_opener_app_open_candidate(payload, AppConfig()) is False

    def test_state7_is_not_candidate(self):
        payload = {"deviceType": 2, "nukiId": 100, "state": 7}
        assert is_opener_app_open_candidate(payload, AppConfig()) is False

    def test_lock_is_not_candidate(self):
        payload = {"deviceType": 0, "nukiId": 200, "state": 1}
        assert is_opener_app_open_candidate(payload, AppConfig()) is False

    def test_opener_id_filter_mismatch(self):
        cfg = AppConfig()
        cfg.nuki.opener_id = 200
        payload = {"deviceType": 2, "nukiId": 100, "state": 1}
        assert is_opener_app_open_candidate(payload, cfg) is False


class TestIsOpenerState7Candidate:
    """#220 gate: state=7 opening requires web disambiguation."""

    def test_state7_is_candidate(self):
        payload = {"deviceType": 2, "nukiId": 100, "state": 7}
        assert is_opener_state7_candidate(payload, AppConfig()) is True

    def test_state1_is_not_candidate(self):
        payload = {"deviceType": 2, "nukiId": 100, "state": 1}
        assert is_opener_state7_candidate(payload, AppConfig()) is False

    def test_lock_is_not_candidate(self):
        payload = {"deviceType": 0, "nukiId": 200, "state": 7}
        assert is_opener_state7_candidate(payload, AppConfig()) is False

    def test_opener_id_filter_mismatch(self):
        cfg = AppConfig()
        cfg.nuki.opener_id = 200
        payload = {"deviceType": 2, "nukiId": 100, "state": 7}
        assert is_opener_state7_candidate(payload, cfg) is False


class TestClassifyState7WithWeb:
    """#220: web-driven disambiguation of state=7 (RTO vs opener button)."""

    @property
    def _FRESH(self):
        """A timestamp just 5 seconds ago — always within the freshness window."""
        from datetime import datetime, timezone, timedelta
        return (datetime.now(timezone.utc) - timedelta(seconds=5)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )

    def _web(self, action, trigger=0):
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"action": action, "trigger": trigger, "source": 0, "date": self._FRESH},
        ]
        return web

    @pytest.mark.asyncio
    async def test_action224_rto(self):
        """action=224 (Auto Unlock / RTO) → ring_to_open."""
        payload = {"deviceType": 2, "nukiId": 100, "state": 7}
        web = self._web(action=224)
        result = await classify_state7_with_web(payload, AppConfig(), web, sleep=AsyncMock())
        assert result == "ring_to_open"

    @pytest.mark.asyncio
    async def test_action3_opener_button(self):
        """action=3 (manual open) → apertura_opener regardless of trigger."""
        payload = {"deviceType": 2, "nukiId": 100, "state": 7}
        web = self._web(action=3, trigger=2)
        result = await classify_state7_with_web(payload, AppConfig(), web, sleep=AsyncMock())
        assert result == "apertura_opener"

    @pytest.mark.asyncio
    async def test_web_exception_falls_back(self):
        """Web API failure → fallback ring_to_open."""
        web = AsyncMock()
        web.get_recent_log.side_effect = Exception("network error")
        payload = {"deviceType": 2, "nukiId": 100, "state": 7}
        result = await classify_state7_with_web(payload, AppConfig(), web, sleep=AsyncMock())
        assert result == "ring_to_open"

    @pytest.mark.asyncio
    async def test_stale_entry_eventually_falls_back(self):
        """If all entries are stale (age > _WEB_FRESH_WINDOW_S), fall back."""
        import nukiblinker.event_router as er
        old_date = "2020-01-01T00:00:00.000Z"
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"action": 224, "trigger": 0, "source": 0, "date": old_date},
        ]
        payload = {"deviceType": 2, "nukiId": 100, "state": 7}
        result = await classify_state7_with_web(payload, AppConfig(), web, sleep=AsyncMock())
        assert result == "ring_to_open"
        assert web.get_recent_log.await_count == er._WEB_MAX_ATTEMPTS


class TestClassifyAppOpenWithWeb:
    """#219: web-driven app-open detection on state=1/state=3."""

    @property
    def _FRESH(self):
        """A timestamp just 5 seconds ago — always within the freshness window."""
        from datetime import datetime, timezone, timedelta
        return (datetime.now(timezone.utc) - timedelta(seconds=5)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )

    @pytest.mark.asyncio
    async def test_fresh_named_action3_dispatches_apertura_con_app(self):
        """Fresh action=3 with user name → apertura_con_app with context."""
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"action": 3, "trigger": 0, "source": 0, "name": "Nico",
             "openerLog": {"activeRto": False}, "date": self._FRESH},
        ]
        payload = {"deviceType": 2, "nukiId": 100, "state": 1}
        event_type, context = await classify_app_open_with_web(
            payload, AppConfig(), web, sleep=AsyncMock()
        )
        assert event_type == "apertura_con_app"
        assert context["name"] == "Nico"
        assert context["name_source"] == "web_api"

    @pytest.mark.asyncio
    async def test_stale_entry_is_ignored(self):
        """Entry older than _WEB_FRESH_WINDOW_S → routine keepalive, return None."""
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"action": 3, "trigger": 0, "source": 0, "name": "Nico",
             "openerLog": {}, "date": "2020-01-01T00:00:00.000Z"},
        ]
        payload = {"deviceType": 2, "nukiId": 100, "state": 1}
        event_type, context = await classify_app_open_with_web(
            payload, AppConfig(), web, sleep=AsyncMock()
        )
        assert event_type is None
        assert context is None

    @pytest.mark.asyncio
    async def test_action224_after_rto_is_ignored(self):
        """Fresh action=224 (RTO) on state=1 → not an app open, ignore."""
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"action": 224, "trigger": 0, "source": 0, "name": "Ele",
             "openerLog": {"activeRto": True}, "date": self._FRESH},
        ]
        payload = {"deviceType": 2, "nukiId": 100, "state": 1}
        event_type, context = await classify_app_open_with_web(
            payload, AppConfig(), web, sleep=AsyncMock()
        )
        assert event_type is None

    @pytest.mark.asyncio
    async def test_anonymous_action3_retried_then_fallback(self):
        """action=3 with empty name → retried; after all attempts uses fallback name."""
        import nukiblinker.event_router as er
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"action": 3, "trigger": 0, "source": 0, "name": "",
             "openerLog": {}, "date": self._FRESH},
        ]
        payload = {"deviceType": 2, "nukiId": 100, "state": 1}
        event_type, context = await classify_app_open_with_web(
            payload, AppConfig(), web, sleep=AsyncMock()
        )
        assert event_type == "apertura_con_app"
        assert context["name_source"] == "fallback"
        assert web.get_recent_log.await_count == er._WEB_MAX_ATTEMPTS

    @pytest.mark.asyncio
    async def test_web_exception_returns_none(self):
        """Web API failure → (None, None) — routine keepalive assumed."""
        web = AsyncMock()
        web.get_recent_log.side_effect = Exception("network error")
        payload = {"deviceType": 2, "nukiId": 100, "state": 1}
        event_type, context = await classify_app_open_with_web(
            payload, AppConfig(), web, sleep=AsyncMock()
        )
        assert event_type is None
        assert context is None


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
        expected_entries = [
            {"smartlockId": 100, "name": "Nico", "trigger": 2, "source": 1},
        ]
        assert result == {
            "name": "Nico",
            "trigger": 2,
            "name_source": "web_api",
            "nuki_web_response": expected_entries,
        }
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
        expected_entries = [
            {"smartlockId": 9129696002, "name": "Nico", "trigger": 5, "source": 1},
        ]
        assert result == {
            "name": "Nico",
            "trigger": 5,
            "name_source": "web_api",
            "nuki_web_response": expected_entries,
        }
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
        expected_entries = [
            {"smartlockId": 100, "name": "Nico", "trigger": None, "source": 1},
        ]
        assert result == {
            "name": "Nico",
            "name_source": "web_api",
            "nuki_web_response": expected_entries,
        }
        assert "trigger" not in result

    @pytest.mark.asyncio
    async def test_web_api_empty_uses_fallback(self):
        """#175: an empty Web log resolves to the fallback (no bridge retry)."""
        web = AsyncMock()
        web.get_recent_log.return_value = []
        result = await resolve_person({"nukiId": 100}, nuki_web=web)
        assert result == {
            "name": "Alguien",
            "name_source": "fallback",
            "nuki_web_response": [],
        }

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
        expected_entries = [{"smartlockId": 100, "trigger": 2, "source": 1}]
        assert result == {
            "name": "Alguien",
            "trigger": 2,
            "name_source": "fallback",
            "nuki_web_response": expected_entries,
        }

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
        expected_entries = [
            {"smartlockId": 100, "trigger": 6, "source": 1},          # most recent: anonymous RTO
            {"smartlockId": 100, "name": "Nico", "trigger": 2},       # older: stale named open
        ]
        assert result == {
            "name": "Alguien",
            "trigger": 6,
            "name_source": "fallback",
            "nuki_web_response": expected_entries,
        }
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
        expected_entries = [
            {"smartlockId": 100, "name": "Celi", "trigger": 0, "source": 0,
             "date": "2026-06-19T08:19:55.000Z"},
        ]
        assert result == {
            "name": "Celi",
            "trigger": 0,
            "name_source": "web_api",
            "event_time": "2026-06-19T08:19:55.000Z",
            "nuki_web_response": expected_entries,
        }
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


# ---------------------------------------------------------------------------
# resolve_person() — matched Web entry date exposed for logging (#204)
# ---------------------------------------------------------------------------


class TestResolvePersonExposesEventTime:
    @pytest.mark.asyncio
    async def test_matched_entry_date_exposed_as_event_time(self):
        """#204: the matched Web entry `date` is returned so the caller can log
        the real event time, not the callback receive time."""
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "name": "Nico", "trigger": 2, "source": 1,
             "date": "2026-06-19T20:11:22.000Z"},
        ]
        result = await resolve_person({"nukiId": 100}, nuki_web=web)
        expected_entries = [
            {"smartlockId": 100, "name": "Nico", "trigger": 2, "source": 1,
             "date": "2026-06-19T20:11:22.000Z"},
        ]
        assert result["name"] == "Nico"
        assert result["event_time"] == "2026-06-19T20:11:22.000Z"
        assert result["nuki_web_response"] == expected_entries

    @pytest.mark.asyncio
    async def test_no_date_means_no_event_time_key(self):
        """An entry without a `date` must not add an `event_time` key — keeps
        the result dict back-compatible with existing exact-match assertions."""
        web = AsyncMock()
        web.get_recent_log.return_value = [
            {"smartlockId": 100, "name": "Nico", "trigger": 2, "source": 1},
        ]
        result = await resolve_person({"nukiId": 100}, nuki_web=web)
        expected_entries = [
            {"smartlockId": 100, "name": "Nico", "trigger": 2, "source": 1},
        ]
        assert result == {
            "name": "Nico",
            "trigger": 2,
            "name_source": "web_api",
            "nuki_web_response": expected_entries,
        }
        assert "event_time" not in result


# ---------------------------------------------------------------------------
# event_time_for_log() — real event time recorded in the Event Log (#204)
# ---------------------------------------------------------------------------


class TestEventTimeForLog:
    def test_fresh_ring_uses_ringaction_timestamp(self):
        """A fresh ring (ringactionState true) logs the real ring time."""
        payload = {
            "ringactionState": True,
            "ringactionTimestamp": "2026-06-20T08:35:00+00:00",
        }
        result = event_time_for_log(payload)
        assert result == datetime(2026, 6, 20, 8, 35, 0, tzinfo=timezone.utc)

    def test_stale_ringaction_timestamp_not_used_for_non_ring(self):
        """#204 regression: a ring_to_open carries yesterday's stale
        ringactionTimestamp with ringactionState false — it must NOT be logged
        as the event time (that was the "strange hours" bug). Without a Web
        match, fall back to receive-time (~now)."""
        payload = {
            "deviceType": 2, "nukiId": 100, "state": 7,
            "ringactionState": False,
            "ringactionTimestamp": "2026-06-19T20:11:22+00:00",  # yesterday
        }
        before = datetime.now(timezone.utc)
        result = event_time_for_log(payload)
        after = datetime.now(timezone.utc)
        assert before <= result <= after  # receive-time, not the stale ts

    def test_ring_to_open_uses_matched_web_date(self):
        """ring_to_open logs the matched Nuki Web entry date from the context."""
        payload = {"deviceType": 2, "nukiId": 100, "state": 7, "ringactionState": False}
        context = {"name": "Nico", "name_source": "web_api",
                   "event_time": "2026-06-20T10:47:00.000Z"}
        result = event_time_for_log(payload, context)
        assert result == datetime(2026, 6, 20, 10, 47, 0, tzinfo=timezone.utc)

    def test_fresh_ring_takes_priority_over_context(self):
        """A fresh ring's ringactionTimestamp wins over a context web date."""
        payload = {
            "ringactionState": True,
            "ringactionTimestamp": "2026-06-20T08:35:00+00:00",
        }
        context = {"event_time": "2026-06-20T10:47:00.000Z"}
        result = event_time_for_log(payload, context)
        assert result == datetime(2026, 6, 20, 8, 35, 0, tzinfo=timezone.utc)

    def test_door_opened_uses_receive_time(self):
        """door_opened (Smart Lock, no Web lookup) logs receive-time (~now)."""
        payload = {"deviceType": 0, "nukiId": 200, "state": 5}
        before = datetime.now(timezone.utc)
        result = event_time_for_log(payload)
        after = datetime.now(timezone.utc)
        assert before <= result <= after

    def test_result_is_timezone_aware_utc(self):
        """All returned times are tz-aware UTC so storage/display stay correct."""
        assert event_time_for_log({}).tzinfo is timezone.utc


# ---------------------------------------------------------------------------
# ringaction_staleness() — bridge buffering / clock-drift signal
# ---------------------------------------------------------------------------


class TestRingactionStaleness:
    NOW = datetime(2026, 6, 20, 10, 0, 0, tzinfo=timezone.utc)

    def test_fresh_ring_recent_timestamp_small_age(self):
        """A fresh ring with a near-instant timestamp has a tiny age."""
        payload = {"ringactionState": True,
                   "ringactionTimestamp": "2026-06-20T09:59:55+00:00"}
        age = ringaction_staleness(payload, now=self.NOW)
        assert age == 5.0
        assert age <= RINGACTION_STALE_THRESHOLD_S

    def test_fresh_ring_old_timestamp_is_stale(self):
        """A fresh ring carrying yesterday's timestamp is flagged stale."""
        payload = {"ringactionState": True,
                   "ringactionTimestamp": "2026-06-19T20:11:22+00:00"}
        age = ringaction_staleness(payload, now=self.NOW)
        assert age > RINGACTION_STALE_THRESHOLD_S

    def test_non_fresh_callback_never_stale(self):
        """#204: a NON-fresh callback (ringactionState false) carrying an old
        last-ring timestamp is normal and must NOT be flagged (returns None)."""
        payload = {"deviceType": 2, "state": 7, "ringactionState": False,
                   "ringactionTimestamp": "2026-06-19T20:11:22+00:00"}
        assert ringaction_staleness(payload, now=self.NOW) is None

    def test_missing_ringaction_state_returns_none(self):
        payload = {"ringactionTimestamp": "2026-06-19T20:11:22+00:00"}
        assert ringaction_staleness(payload, now=self.NOW) is None

    def test_missing_or_invalid_timestamp_returns_none(self):
        assert ringaction_staleness({"ringactionState": True}, now=self.NOW) is None
        assert ringaction_staleness(
            {"ringactionState": True, "ringactionTimestamp": "not-a-date"},
            now=self.NOW,
        ) is None

    def test_future_timestamp_is_negative_not_stale(self):
        """A future-dated timestamp yields a negative age (never stale)."""
        payload = {"ringactionState": True,
                   "ringactionTimestamp": "2026-06-20T10:01:00+00:00"}
        age = ringaction_staleness(payload, now=self.NOW)
        assert age == -60.0

    def test_defaults_now_to_current_time(self):
        """Without an explicit now, a just-now fresh ring is not stale."""
        ts = datetime.now(timezone.utc).isoformat()
        age = ringaction_staleness({"ringactionState": True, "ringactionTimestamp": ts})
        assert age is not None
        assert age < RINGACTION_STALE_THRESHOLD_S
