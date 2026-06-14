"""Tests for night mode service."""

import pytest
from datetime import time

from nukiblinker.night_mode import NightMode
from nukiblinker.config import EventRuleConfig, BlinkConfig, AudioConfig


def _fake_datetime(year=None, month=None, day=None, hour=0, minute=0):
    """Return a datetime subclass whose now() reports a fixed time.

    Subclassing keeps classmethods like combine() and today() functional.
    """
    import datetime as _dt

    class FakeDateTime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            if year is None:
                t = _dt.date.today()
                return cls(t.year, t.month, t.day, hour, minute)
            return cls(year, month, day, hour, minute)

    return FakeDateTime


class TestNightMode:
    """Test cases for NightMode."""

    def test_init_default(self):
        """Test NightMode initialization with default values."""
        night_mode = NightMode()

        assert night_mode.start_time_str == "22:00"
        assert night_mode.end_time_str == "07:00"
        assert night_mode.brightness_factor == 0.3
        assert night_mode.grace_minutes == 5
        assert night_mode.is_enabled() is True

    def test_init_custom(self):
        """Test NightMode initialization with custom values."""
        night_mode = NightMode(
            start_time="23:00",
            end_time="06:30",
            brightness_factor=0.5,
            grace_minutes=10
        )

        assert night_mode.start_time_str == "23:00"
        assert night_mode.end_time_str == "06:30"
        assert night_mode.brightness_factor == 0.5
        assert night_mode.grace_minutes == 10
        assert night_mode.is_enabled() is True

    def test_init_invalid_time_format(self):
        """Test NightMode initialization with invalid time format."""
        night_mode = NightMode(start_time="invalid", end_time="07:00")

        # Should be disabled when time format is invalid
        assert night_mode.is_enabled() is False
        assert night_mode.start_time is None
        assert night_mode.end_time is None

    def test_is_enabled_false_when_disabled(self):
        """Test is_enabled returns False when times are invalid."""
        night_mode = NightMode(start_time="25:00", end_time="07:00")
        assert night_mode.is_enabled() is False

    def test_is_night_time_same_day_range(self):
        """Test night time detection for same-day range."""
        # Test with a range that doesn't cross midnight (e.g., 01:00 to 05:00)
        night_mode = NightMode(start_time="01:00", end_time="05:00", grace_minutes=0)

        # Test inside range (2:30 AM)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(hour=2, minute=30))
            assert night_mode.is_night_time() is True

        # Test before range (0:30 AM)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(hour=0, minute=30))
            assert night_mode.is_night_time() is False

        # Test after range (6:30 AM)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(hour=6, minute=30))
            assert night_mode.is_night_time() is False

    def test_is_night_time_overnight_range(self):
        """Test night time detection for overnight range."""
        # Test with range that crosses midnight (e.g., 22:00 to 07:00)
        night_mode = NightMode(start_time="22:00", end_time="07:00", grace_minutes=0)

        # Test evening (inside range, 11:30 PM)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(hour=23, minute=30))
            assert night_mode.is_night_time() is True

        # Test morning (inside range, 3:30 AM)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(hour=3, minute=30))
            assert night_mode.is_night_time() is True

        # Test afternoon (outside range, 2:30 PM)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(hour=14, minute=30))
            assert night_mode.is_night_time() is False

    def test_is_night_time_with_grace_period(self):
        """Test night time detection with grace period."""
        night_mode = NightMode(start_time="22:00", end_time="07:00", grace_minutes=5)

        # Test just before start time (21:56, within grace period)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(hour=21, minute=56))
            assert night_mode.is_night_time() is True  # Should be night due to grace period

        # Test just after end time (7:03, within grace period)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(hour=7, minute=3))
            assert night_mode.is_night_time() is True  # Should be night due to grace period

    def test_is_night_time_grace_wraps_past_midnight(self):
        """Regression: grace period that crosses midnight must wrap correctly.

        With start 00:02 and a 5-minute grace, the effective window starts at
        23:57 the previous day. The old naive time() arithmetic evaluated this
        as not-night at 23:58.
        """
        night_mode = NightMode(start_time="00:02", end_time="06:00", grace_minutes=5)

        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(hour=23, minute=58))
            assert night_mode.is_night_time() is True  # inside grace before midnight

        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(hour=23, minute=50))
            assert night_mode.is_night_time() is False  # before the grace window

    def test_apply_night_mode_disabled(self):
        """Test apply_night_mode when night mode is disabled."""
        night_mode = NightMode(start_time="invalid", end_time="07:00")

        rule = EventRuleConfig(
            blink=BlinkConfig(mode="long"),
            audio=AudioConfig(enabled=True),
            homekit=True
        )

        result = night_mode.apply_night_mode(rule)

        # Should return original rule unchanged
        assert result is rule
        assert result.audio.enabled is True

    def test_apply_night_mode_not_night_time(self):
        """Test apply_night_mode when it's not night time."""
        night_mode = NightMode(start_time="01:00", end_time="05:00", grace_minutes=0)

        # Mock current time as 10:00 (outside night range)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(hour=10, minute=0))

            rule = EventRuleConfig(
                blink=BlinkConfig(mode="long"),
                audio=AudioConfig(enabled=True),
                homekit=True
            )

            result = night_mode.apply_night_mode(rule)

            # Should return original rule unchanged
            assert result is rule
            assert result.audio.enabled is True

    def test_apply_night_mode_during_night_time(self):
        """Test apply_night_mode during night time disables audio but keeps blink."""
        night_mode = NightMode(start_time="22:00", end_time="07:00", brightness_factor=0.5, grace_minutes=0)

        # Mock current time as 23:00 (inside night range)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(hour=23, minute=0))

            original_rule = EventRuleConfig(
                blink=BlinkConfig(mode="long"),
                audio=AudioConfig(enabled=True, mode="tts"),
                homekit=True
            )

            result = night_mode.apply_night_mode(original_rule)

            # Should be a different object (deep copy)
            assert result is not original_rule

            # Audio should be disabled
            assert result.audio.enabled is False

            # Built-in blink mode is unchanged (bridge controls brightness)
            assert result.blink.mode == "long"

            # HomeKit should remain enabled
            assert result.homekit is True

    def test_apply_night_mode_long_mode(self):
        """Test apply_night_mode with long blink mode leaves blink untouched."""
        night_mode = NightMode(start_time="22:00", end_time="07:00", grace_minutes=0)

        # Mock current time as 23:00 (inside night range)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(hour=23, minute=0))

            rule = EventRuleConfig(
                blink=BlinkConfig(mode="long"),
                audio=AudioConfig(enabled=True),
                homekit=True
            )

            result = night_mode.apply_night_mode(rule)

            # Audio should be disabled
            assert result.audio.enabled is False

            # Blink mode should remain unchanged (no brightness to modify)
            assert result.blink.mode == "long"

            # HomeKit should remain enabled
            assert result.homekit is True

    def test_apply_night_mode_none_mode(self):
        """Test apply_night_mode with none blink mode."""
        night_mode = NightMode(start_time="22:00", end_time="07:00", grace_minutes=0)

        # Mock current time as 23:00 (inside night range)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(hour=23, minute=0))

            rule = EventRuleConfig(
                blink=BlinkConfig(mode="none"),  # No blink
                audio=AudioConfig(enabled=True),
                homekit=True
            )

            result = night_mode.apply_night_mode(rule)

            # Audio should be disabled
            assert result.audio.enabled is False

            # None mode should remain unchanged
            assert result.blink.mode == "none"

            # HomeKit should remain enabled
            assert result.homekit is True

    def test_get_next_change_time(self):
        """Test getting the next night mode change time."""
        night_mode = NightMode(start_time="22:00", end_time="07:00", grace_minutes=0)

        # Mock current time as 10:00 (day mode)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(2023, 6, 15, 10, 0))

            next_change = night_mode.get_next_change_time()

            # Should be today at 22:00
            assert next_change is not None
            assert next_change.hour == 22
            assert next_change.minute == 0
            assert next_change.date().day == 15

        # Mock current time as 23:00 (night mode)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(2023, 6, 15, 23, 0))

            next_change = night_mode.get_next_change_time()

            # Should be tomorrow at 07:00
            assert next_change is not None
            assert next_change.hour == 7
            assert next_change.minute == 0
            assert next_change.date().day == 16  # Next day

    def test_get_next_change_time_same_day_range(self):
        """Next change is correct for a range that does not cross midnight."""
        night_mode = NightMode(start_time="01:00", end_time="05:00", grace_minutes=0)

        # Before the window (00:30) -> next change is today's start (01:00).
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(2023, 6, 15, 0, 30))
            nc = night_mode.get_next_change_time()
            assert (nc.day, nc.hour, nc.minute) == (15, 1, 0)

        # Inside the window (02:30) -> next change is today's end (05:00).
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(2023, 6, 15, 2, 30))
            nc = night_mode.get_next_change_time()
            assert (nc.day, nc.hour, nc.minute) == (15, 5, 0)

        # After the window (10:00) -> next change is tomorrow's start (01:00).
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(2023, 6, 15, 10, 0))
            nc = night_mode.get_next_change_time()
            assert (nc.day, nc.hour, nc.minute) == (16, 1, 0)

    def test_get_next_change_time_grace_boundary_consistency(self):
        """Inside the grace window, active state and next_change must agree.

        With start 22:00 + 5 min grace, 21:57 is already night. The next
        change must therefore be when night *ends*, grace-adjusted to
        07:05 (not the raw 07:00).
        """
        night_mode = NightMode(start_time="22:00", end_time="07:00", grace_minutes=5)

        # 21:57: within the pre-start grace -> already night.
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(2023, 6, 15, 21, 57))
            assert night_mode.is_night_time() is True
            nc = night_mode.get_next_change_time()
            # Night ends next day at end_time + grace = 07:05.
            assert (nc.day, nc.hour, nc.minute) == (16, 7, 5)

        # 21:50: before the grace window -> still day, next change is the
        # grace-adjusted start (21:55) today.
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(2023, 6, 15, 21, 50))
            assert night_mode.is_night_time() is False
            nc = night_mode.get_next_change_time()
            assert (nc.day, nc.hour, nc.minute) == (15, 21, 55)

        # 07:03: within the post-end grace -> still night, next change is the
        # grace-adjusted end (07:05) today.
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(2023, 6, 15, 7, 3))
            assert night_mode.is_night_time() is True
            nc = night_mode.get_next_change_time()
            assert (nc.day, nc.hour, nc.minute) == (15, 7, 5)

    def test_get_next_change_time_disabled(self):
        """Test getting next change time when night mode is disabled."""
        night_mode = NightMode(start_time="invalid", end_time="07:00")

        next_change = night_mode.get_next_change_time()
        assert next_change is None

    def test_parse_time_valid(self):
        """Test parsing valid time strings."""
        night_mode = NightMode()

        # Test various valid formats
        assert night_mode._parse_time("00:00") == time(0, 0)
        assert night_mode._parse_time("12:30") == time(12, 30)
        assert night_mode._parse_time("23:59") == time(23, 59)

    def test_parse_time_invalid(self):
        """Test parsing invalid time strings."""
        night_mode = NightMode()

        # Test various invalid formats
        with pytest.raises(ValueError):
            night_mode._parse_time("24:00")  # Invalid hour

        with pytest.raises(ValueError):
            night_mode._parse_time("12:60")  # Invalid minute

        with pytest.raises(ValueError):
            night_mode._parse_time("12:30:45")  # Invalid format

        with pytest.raises(ValueError):
            night_mode._parse_time("invalid")  # Invalid format

        with pytest.raises(ValueError):
            night_mode._parse_time("12.30")  # Invalid separator

    def test_update_settings(self):
        """Test updating night mode settings."""
        night_mode = NightMode()

        # Update individual settings
        night_mode.update_settings(start_time="23:00")
        assert night_mode.start_time_str == "23:00"
        assert night_mode.start_time == time(23, 0)

        night_mode.update_settings(end_time="06:30")
        assert night_mode.end_time_str == "06:30"
        assert night_mode.end_time == time(6, 30)

        night_mode.update_settings(brightness_factor=0.7)
        assert night_mode.brightness_factor == 0.7

        night_mode.update_settings(grace_minutes=15)
        assert night_mode.grace_minutes == 15

    def test_update_settings_bounds_checking(self):
        """Test that settings updates respect bounds."""
        night_mode = NightMode()

        # Test brightness factor bounds
        night_mode.update_settings(brightness_factor=-0.5)
        assert night_mode.brightness_factor == 0.0  # Should be clamped to 0.0

        night_mode.update_settings(brightness_factor=1.5)
        assert night_mode.brightness_factor == 1.0  # Should be clamped to 1.0

        # Test grace minutes bounds
        night_mode.update_settings(grace_minutes=-5)
        assert night_mode.grace_minutes == 0  # Should be clamped to 0

    def test_get_status(self):
        """Test getting night mode status."""
        night_mode = NightMode(start_time="22:00", end_time="07:00", brightness_factor=0.3, grace_minutes=5)

        # Mock current time as 10:00 (day mode)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(2023, 6, 15, 10, 0))

            status = night_mode.get_status()

            assert status["enabled"] is True
            assert status["active"] is False
            assert status["start_time"] == "22:00"
            assert status["end_time"] == "07:00"
            assert status["brightness_factor"] == 0.3
            assert status["grace_minutes"] == 5
            assert "next_change" in status
            assert "current_time" in status
