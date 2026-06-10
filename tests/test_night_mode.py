"""Tests for night mode service."""

import pytest
from datetime import datetime, time, timedelta

from nukiblinker.night_mode import NightMode
from nukiblinker.config import EventRuleConfig, BlinkConfig, AudioConfig, CustomBlinkConfig


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
        
        # Create times for testing
        night_time_inside = time(2, 30)  # 2:30 AM - should be night
        night_time_before = time(0, 30)  # 12:30 AM - should be day
        night_time_after = time(6, 30)   # 6:30 AM - should be day
        
        # Mock datetime.now() to return specific times
        class MockDateTime:
            @staticmethod
            def now():
                class MockNow:
                    def time(self):
                        return night_time_inside
                return MockNow()
        
        # Test inside range
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', MockDateTime)
            assert night_mode.is_night_time() is True
        
        # Test before range
        class MockDateTimeBefore:
            @staticmethod
            def now():
                class MockNow:
                    def time(self):
                        return night_time_before
                return MockNow()
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', MockDateTimeBefore)
            assert night_mode.is_night_time() is False
        
        # Test after range
        class MockDateTimeAfter:
            @staticmethod
            def now():
                class MockNow:
                    def time(self):
                        return night_time_after
                return MockNow()
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', MockDateTimeAfter)
            assert night_mode.is_night_time() is False
    
    def test_is_night_time_overnight_range(self):
        """Test night time detection for overnight range."""
        # Test with range that crosses midnight (e.g., 22:00 to 07:00)
        night_mode = NightMode(start_time="22:00", end_time="07:00", grace_minutes=0)
        
        # Create times for testing
        night_time_evening = time(23, 30)  # 11:30 PM - should be night
        night_time_morning = time(3, 30)   # 3:30 AM - should be night
        day_time_afternoon = time(14, 30)  # 2:30 PM - should be day
        
        # Test evening (inside range)
        class MockDateTimeEvening:
            @staticmethod
            def now():
                class MockNow:
                    def time(self):
                        return night_time_evening
                return MockNow()
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', MockDateTimeEvening)
            assert night_mode.is_night_time() is True
        
        # Test morning (inside range)
        class MockDateTimeMorning:
            @staticmethod
            def now():
                class MockNow:
                    def time(self):
                        return night_time_morning
                return MockNow()
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', MockDateTimeMorning)
            assert night_mode.is_night_time() is True
        
        # Test afternoon (outside range)
        class MockDateTimeAfternoon:
            @staticmethod
            def now():
                class MockNow:
                    def time(self):
                        return day_time_afternoon
                return MockNow()
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', MockDateTimeAfternoon)
            assert night_mode.is_night_time() is False
    
    def test_is_night_time_with_grace_period(self):
        """Test night time detection with grace period."""
        night_mode = NightMode(start_time="22:00", end_time="07:00", grace_minutes=5)
        
        # Test just before start time (within grace period)
        grace_time_before = time(21, 56)  # 21:56 - 4 minutes before 22:00
        
        class MockDateTimeGraceBefore:
            @staticmethod
            def now():
                class MockNow:
                    def time(self):
                        return grace_time_before
                return MockNow()
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', MockDateTimeGraceBefore)
            assert night_mode.is_night_time() is True  # Should be night due to grace period
        
        # Test just after end time (within grace period)
        grace_time_after = time(7, 3)  # 7:03 - 3 minutes after 7:00
        
        class MockDateTimeGraceAfter:
            @staticmethod
            def now():
                class MockNow:
                    def time(self):
                        return grace_time_after
                return MockNow()
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', MockDateTimeGraceAfter)
            assert night_mode.is_night_time() is True  # Should be night due to grace period
    
    def test_apply_night_mode_disabled(self):
        """Test apply_night_mode when night mode is disabled."""
        night_mode = NightMode(start_time="invalid", end_time="07:00")
        
        rule = EventRuleConfig(
            blink=BlinkConfig(mode="custom"),
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
        class MockDateTime:
            @staticmethod
            def now():
                class MockNow:
                    def time(self):
                        return time(10, 0)
                return MockNow()
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', MockDateTime)
            
            rule = EventRuleConfig(
                blink=BlinkConfig(mode="custom"),
                audio=AudioConfig(enabled=True),
                homekit=True
            )
            
            result = night_mode.apply_night_mode(rule)
            
            # Should return original rule unchanged
            assert result is rule
            assert result.audio.enabled is True
    
    def test_apply_night_mode_during_night_time(self):
        """Test apply_night_mode during night time."""
        night_mode = NightMode(start_time="22:00", end_time="07:00", brightness_factor=0.5, grace_minutes=0)
        
        # Mock current time as 23:00 (inside night range)
        class MockDateTime:
            @staticmethod
            def now():
                class MockNow:
                    def time(self):
                        return time(23, 0)
                return MockNow()
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', MockDateTime)
            
            original_rule = EventRuleConfig(
                blink=BlinkConfig(
                    mode="custom",
                    custom=CustomBlinkConfig(
                        hue=25500,
                        saturation=254,
                        brightness=254,  # Full brightness
                        flashes=3,
                        interval_ms=500
                    )
                ),
                audio=AudioConfig(enabled=True, mode="tts"),
                homekit=True
            )
            
            result = night_mode.apply_night_mode(original_rule)
            
            # Should be a different object (deep copy)
            assert result is not original_rule
            
            # Audio should be disabled
            assert result.audio.enabled is False
            
            # Brightness should be reduced
            assert result.blink.custom.brightness == int(254 * 0.5)  # 127
            
            # HomeKit should remain enabled
            assert result.homekit is True
            
            # Other properties should be unchanged
            assert result.blink.custom.hue == 25500
            assert result.blink.custom.saturation == 254
            assert result.blink.custom.flashes == 3
    
    def test_apply_night_mode_alert_mode(self):
        """Test apply_night_mode with alert blink mode."""
        night_mode = NightMode(start_time="22:00", end_time="07:00", grace_minutes=0)
        
        # Mock current time as 23:00 (inside night range)
        class MockDateTime:
            @staticmethod
            def now():
                class MockNow:
                    def time(self):
                        return time(23, 0)
                return MockNow()
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', MockDateTime)
            
            rule = EventRuleConfig(
                blink=BlinkConfig(mode="alert"),  # Alert mode
                audio=AudioConfig(enabled=True),
                homekit=True
            )
            
            result = night_mode.apply_night_mode(rule)
            
            # Audio should be disabled
            assert result.audio.enabled is False
            
            # Alert mode should remain unchanged (no brightness to modify)
            assert result.blink.mode == "alert"
            
            # HomeKit should remain enabled
            assert result.homekit is True
    
    def test_apply_night_mode_none_mode(self):
        """Test apply_night_mode with none blink mode."""
        night_mode = NightMode(start_time="22:00", end_time="07:00", grace_minutes=0)
        
        # Mock current time as 23:00 (inside night range)
        class MockDateTime:
            @staticmethod
            def now():
                class MockNow:
                    def time(self):
                        return time(23, 0)
                return MockNow()
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', MockDateTime)
            
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
        class MockDateTimeDay:
            @staticmethod
            def now():
                return datetime(2023, 6, 15, 10, 0)  # 10:00 AM
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', MockDateTimeDay)
            
            next_change = night_mode.get_next_change_time()
            
            # Should be today at 22:00
            assert next_change is not None
            assert next_change.hour == 22
            assert next_change.minute == 0
            assert next_change.date().day == 15
        
        # Mock current time as 23:00 (night mode)
        class MockDateTimeNight:
            @staticmethod
            def now():
                return datetime(2023, 6, 15, 23, 0)  # 11:00 PM
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', MockDateTimeNight)
            
            next_change = night_mode.get_next_change_time()
            
            # Should be tomorrow at 07:00
            assert next_change is not None
            assert next_change.hour == 7
            assert next_change.minute == 0
            assert next_change.date().day == 16  # Next day
    
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
        class MockDateTime:
            @staticmethod
            def now():
                return datetime(2023, 6, 15, 10, 0)
        
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', MockDateTime)
            
            status = night_mode.get_status()
            
            assert status["enabled"] is True
            assert status["active"] is False
            assert status["start_time"] == "22:00"
            assert status["end_time"] == "07:00"
            assert status["brightness_factor"] == 0.3
            assert status["grace_minutes"] == 5
            assert "next_change" in status
            assert "current_time" in status
