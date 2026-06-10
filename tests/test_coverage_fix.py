"""Additional tests to improve code coverage for CI."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from nukiblinker.event_validator import EventValidator, ValidationResult
from nukiblinker.night_mode import NightMode
from nukiblinker.event_log import EventLog, EventLogEntry


class TestCoverageImprovement:
    """Additional tests to improve coverage for CI pipeline."""
    
    def test_event_validator_edge_cases(self):
        """Test edge cases for EventValidator to improve coverage."""
        validator = EventValidator(max_delay_seconds=60)
        
        # Test with empty payload
        result = validator.validate_event({})
        assert result.valid is True
        assert result.delay_seconds == 0.0
        assert result.reason is None
        
        # Test with None payload
        result = validator.validate_event(None)
        assert result.valid is True
        assert result.delay_seconds == 0.0
        assert result.reason is None
        
        # Test _parse_timestamp_value with invalid types
        with pytest.raises(ValueError):
            validator._parse_timestamp_value([])
        
        # Test _extract_timestamp with empty dict
        result = validator._extract_timestamp({})
        assert result is None
    
    def test_night_mode_edge_cases(self):
        """Test edge cases for NightMode to improve coverage."""
        night_mode = NightMode(
            start_time="22:00",
            end_time="07:00",
            brightness_factor=0.5,
            grace_minutes=5
        )
        
        # Test with invalid time format
        try:
            night_mode._parse_time("invalid")
        except ValueError:
            pass  # Expected
        
        # Test _adjust_brightness with None
        result = night_mode._adjust_brightness(None)
        assert result is None
        
        # Test _adjust_brightness with invalid dict
        result = night_mode._adjust_brightness({"invalid": "data"})
        assert result == {"invalid": "data"}
        
        # Test _should_suppress_audio with None
        result = night_mode._should_suppress_audio(None)
        assert result is False
    
    def test_event_log_edge_cases(self):
        """Test edge cases for EventLog to improve coverage."""
        event_log = EventLog(max_entries=10, persist_to_file=False)
        
        # Test log_event with minimal data
        event_log.log_event(
            payload={"test": "data"},
            event_type="test",
            actions=["action1"],
            validation_result=ValidationResult(valid=True, delay_seconds=0.0)
        )
        
        assert len(event_log.entries) == 1
        
        # Test get_recent_events with limit larger than entries
        events = event_log.get_recent_events(limit=100)
        assert len(events) == 1
        
        # Test get_recent_events with offset
        events = event_log.get_recent_events(limit=10, offset=1)
        assert len(events) == 0
        
        # Test export_to_csv with no entries
        empty_log = EventLog(max_entries=10, persist_to_file=False)
        csv_content = empty_log.export_to_csv()
        assert "Timestamp" in csv_content
        assert len(csv_content.strip().split('\n')) == 1  # Header only
        
        # Test _cleanup_old_entries when no cleanup needed
        event_log._cleanup_old_entries()
        assert len(event_log.entries) == 1
    
    def test_event_log_entry_serialization(self):
        """Test EventLogEntry serialization for coverage."""
        entry = EventLogEntry(
            timestamp=datetime.now(timezone.utc),
            event_type="test",
            payload={"key": "value"},
            actions=["action1"],
            validation_result=ValidationResult(valid=True, delay_seconds=1.0),
            processing_time_ms=100.5
        )
        
        # Test to_dict method
        data = entry.to_dict()
        assert data["event_type"] == "test"
        assert data["payload"]["key"] == "value"
        assert data["validation_result"]["valid"] is True
        assert data["processing_time_ms"] == 100.5
    
    @patch('nukiblinker.event_log.datetime')
    def test_event_log_retention_cleanup(self, mock_datetime):
        """Test event log cleanup based on retention."""
        # Mock current time
        now = datetime.now(timezone.utc)
        mock_datetime.now.return_value = now
        
        event_log = EventLog(max_entries=100, retention_days=1, persist_to_file=False)
        
        # Add an old event (2 days ago)
        old_time = now.replace(day=now.day - 2)
        old_entry = EventLogEntry(
            timestamp=old_time,
            event_type="old",
            payload={},
            actions=[],
            validation_result=ValidationResult(valid=True, delay_seconds=0.0)
        )
        event_log.entries.append(old_entry)
        
        # Add a recent event
        recent_entry = EventLogEntry(
            timestamp=now,
            event_type="recent",
            payload={},
            actions=[],
            validation_result=ValidationResult(valid=True, delay_seconds=0.0)
        )
        event_log.entries.append(recent_entry)
        
        # Run cleanup
        event_log._cleanup_old_entries()
        
        # Should only have the recent entry
        assert len(event_log.entries) == 1
        assert event_log.entries[0].event_type == "recent"
    
    def test_night_mode_status(self):
        """Test NightMode status method for coverage."""
        night_mode = NightMode(
            start_time="22:00",
            end_time="07:00",
            brightness_factor=0.5,
            grace_minutes=5
        )
        
        # Test status method
        status = night_mode.get_status()
        assert "enabled" in status
        assert "active" in status
        assert "start_time" in status
        assert "end_time" in status
        assert "brightness_factor" in status
        assert "grace_minutes" in status
