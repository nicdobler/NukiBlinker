"""Tests for event validation service."""

import pytest
from datetime import datetime, timezone, timedelta
from nukiblinker.event_validator import EventValidator


class TestEventValidator:
    """Test cases for EventValidator."""

    def test_init_default(self):
        """Test validator initialization with default values."""
        validator = EventValidator()
        assert validator.max_delay_seconds == 60

    def test_init_custom(self):
        """Test validator initialization with custom values."""
        validator = EventValidator(max_delay_seconds=120)
        assert validator.max_delay_seconds == 120

    def test_validate_event_valid_recent(self):
        """Test validation of recent valid event."""
        validator = EventValidator(max_delay_seconds=60)

        # Event from 30 seconds ago
        event_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        payload = {"timestamp": event_time.timestamp()}

        result = validator.validate_event(payload)

        assert result.valid is True
        assert result.delay_seconds == pytest.approx(30.0, rel=1e-1)
        assert result.reason is None

    def test_validate_event_invalid_old(self):
        """Test validation of old invalid event."""
        validator = EventValidator(max_delay_seconds=60)

        # Event from 2 minutes ago
        event_time = datetime.now(timezone.utc) - timedelta(minutes=2)
        payload = {"timestamp": event_time.timestamp()}

        result = validator.validate_event(payload)

        assert result.valid is False
        assert result.delay_seconds == pytest.approx(120.0, rel=1e-1)
        assert "Event too old" in result.reason

    def test_validate_event_no_timestamp(self):
        """Test validation of event without timestamp."""
        validator = EventValidator(max_delay_seconds=60)
        payload = {"deviceType": 2, "state": 7}

        result = validator.validate_event(payload)

        assert result.valid is True
        assert result.delay_seconds == 0.0
        assert result.reason is None

    def test_validate_event_future_timestamp_small(self):
        """Test validation of event with small future timestamp (clock sync)."""
        validator = EventValidator(max_delay_seconds=60)

        # Event 1 minute in the future (within grace period)
        event_time = datetime.now(timezone.utc) + timedelta(minutes=1)
        payload = {"timestamp": event_time.timestamp()}

        result = validator.validate_event(payload)

        assert result.valid is True
        assert result.delay_seconds == pytest.approx(-60.0, rel=1e-1)
        assert result.reason is None

    def test_validate_event_future_timestamp_large(self):
        """Test validation of event with large future timestamp."""
        validator = EventValidator(max_delay_seconds=60)

        # Event 10 minutes in the future (beyond grace period)
        event_time = datetime.now(timezone.utc) + timedelta(minutes=10)
        payload = {"timestamp": event_time.timestamp()}

        result = validator.validate_event(payload)

        assert result.valid is False
        assert result.delay_seconds == pytest.approx(-600.0, rel=1e-1)
        assert "too far in the future" in result.reason

    def test_validate_event_timestamp_milliseconds(self):
        """Test validation with millisecond timestamp."""
        validator = EventValidator(max_delay_seconds=60)

        # Event from 30 seconds ago with millisecond timestamp
        event_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        payload = {"timestamp": int(event_time.timestamp() * 1000)}

        result = validator.validate_event(payload)

        assert result.valid is True
        assert result.delay_seconds == pytest.approx(30.0, rel=1e-1)

    def test_validate_event_timestamp_iso_string(self):
        """Test validation with ISO format timestamp string."""
        validator = EventValidator(max_delay_seconds=60)

        # Event from 30 seconds ago with ISO string
        event_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        payload = {"timestamp": event_time.isoformat()}

        result = validator.validate_event(payload)

        assert result.valid is True
        assert result.delay_seconds == pytest.approx(30.0, rel=1e-1)

    def test_validate_event_timestamp_string_number(self):
        """Test validation with timestamp as string number."""
        validator = EventValidator(max_delay_seconds=60)

        # Event from 30 seconds ago with string timestamp
        event_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        payload = {"timestamp": str(int(event_time.timestamp()))}

        result = validator.validate_event(payload)

        assert result.valid is True
        assert result.delay_seconds == pytest.approx(30.0, rel=1e-1)

    def test_validate_event_invalid_timestamp_format(self):
        """Test validation with invalid timestamp format."""
        validator = EventValidator(max_delay_seconds=60)
        payload = {"timestamp": "invalid-timestamp"}

        result = validator.validate_event(payload)

        # Should fall back to valid when parsing fails (no timestamp found)
        assert result.valid is True
        assert result.delay_seconds == 0.0
        assert result.reason is None  # Valid events have no reason

    def test_validate_event_alternative_timestamp_field(self):
        """Test validation with alternative timestamp field names."""
        validator = EventValidator(max_delay_seconds=60)

        # Event with 'time' field instead of 'timestamp'
        event_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        payload = {"time": event_time.timestamp()}

        result = validator.validate_event(payload)

        assert result.valid is True
        assert result.delay_seconds == pytest.approx(30.0, rel=1e-1)

    def test_validate_event_edge_case_threshold(self):
        """Test validation exactly at the threshold boundary."""
        validator = EventValidator(max_delay_seconds=60)

        # Event just inside the threshold (test runtime adds a few ms,
        # so exactly 60s would flakily exceed the limit)
        event_time = datetime.now(timezone.utc) - timedelta(seconds=59)
        payload = {"timestamp": event_time.timestamp()}

        result = validator.validate_event(payload)

        assert result.valid is True
        assert result.delay_seconds == pytest.approx(59.0, rel=1e-1)
        assert result.reason is None

    def test_validate_event_edge_case_just_over_threshold(self):
        """Test validation just over the threshold boundary."""
        validator = EventValidator(max_delay_seconds=60)

        # Event 60.1 seconds ago
        event_time = datetime.now(timezone.utc) - timedelta(seconds=60.1)
        payload = {"timestamp": event_time.timestamp()}

        result = validator.validate_event(payload)

        assert result.valid is False
        assert result.delay_seconds == pytest.approx(60.1, rel=1e-1)
        assert "Event too old" in result.reason

    def test_extract_timestamp_unix_seconds(self):
        """Test timestamp extraction from Unix seconds."""
        validator = EventValidator()
        event_time = datetime.now(timezone.utc)
        payload = {"timestamp": event_time.timestamp()}

        extracted = validator._extract_timestamp(payload)

        assert extracted is not None
        assert extracted.tzinfo == timezone.utc
        assert extracted == pytest.approx(event_time, rel=1e-6)

    def test_extract_timestamp_unix_milliseconds(self):
        """Test timestamp extraction from Unix milliseconds."""
        validator = EventValidator()
        # Use a fixed time to avoid precision issues
        event_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        payload = {"timestamp": int(event_time.timestamp() * 1000)}

        extracted = validator._extract_timestamp(payload)

        assert extracted is not None
        assert extracted.tzinfo == timezone.utc
        assert extracted == event_time

    def test_extract_timestamp_iso_format(self):
        """Test timestamp extraction from ISO format."""
        validator = EventValidator()
        event_time = datetime.now(timezone.utc)
        payload = {"timestamp": event_time.isoformat()}

        extracted = validator._extract_timestamp(payload)

        assert extracted is not None
        assert extracted.tzinfo == timezone.utc
        assert extracted == pytest.approx(event_time, rel=1e-6)

    def test_extract_timestamp_none(self):
        """Test timestamp extraction when no timestamp present."""
        validator = EventValidator()
        payload = {"deviceType": 2, "state": 7}

        extracted = validator._extract_timestamp(payload)

        assert extracted is None

    def test_extract_timestamp_invalid_type(self):
        """Test timestamp extraction with invalid type."""
        validator = EventValidator()
        payload = {"timestamp": {"invalid": "object"}}

        extracted = validator._extract_timestamp(payload)

        assert extracted is None
