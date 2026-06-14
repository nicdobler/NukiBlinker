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

    def test_active_ring_prefers_ringaction_timestamp(self):
        """#115: a genuine ring is valid even when the lock-state ``timestamp`` is stale.

        Real Opener ring callbacks carry a stale top-level ``timestamp`` (the
        "retrieval of this lock state") plus the actual ring time in
        ``ringactionTimestamp``. Before the fix the validator used the stale
        ``timestamp`` and rejected every real ring as "too old"; it must now
        validate against ``ringactionTimestamp`` while a ring action is active.
        """
        validator = EventValidator(max_delay_seconds=60)
        now = datetime.now(timezone.utc)
        payload = {
            "deviceType": 2,
            "nukiId": 12345,
            "ringactionState": True,
            "ringactionTimestamp": (now - timedelta(seconds=5)).isoformat(),
            # Stale lock-state timestamp (10 minutes old) — would fail validation.
            "timestamp": (now - timedelta(minutes=10)).isoformat(),
        }

        result = validator.validate_event(payload)

        assert result.valid is True
        assert result.delay_seconds == pytest.approx(5.0, abs=2.0)
        assert result.reason is None

    def test_inactive_ring_action_uses_lock_state_timestamp(self):
        """Without an active ring action, fall back to the lock-state ``timestamp``.

        A non-ring callback (e.g. door opened) may still carry an old
        ``ringactionTimestamp`` from a previous ring; it must be ignored when
        ``ringactionState`` is false so we validate against the event's own
        ``timestamp``.
        """
        validator = EventValidator(max_delay_seconds=60)
        now = datetime.now(timezone.utc)
        payload = {
            "deviceType": 0,
            "nukiId": 67890,
            "ringactionState": False,
            "ringactionTimestamp": (now - timedelta(hours=2)).isoformat(),
            "timestamp": (now - timedelta(seconds=10)).isoformat(),
        }

        extracted = validator._extract_timestamp(payload)

        assert extracted is not None
        assert abs((extracted - (now - timedelta(seconds=10))).total_seconds()) < 1

    def test_naive_iso_string_is_normalized_to_utc(self):
        """#143: a naive ISO string (no tz) is parsed as UTC, not left naive."""
        validator = EventValidator()
        payload = {"timestamp": "2026-06-14T10:00:00"}

        extracted = validator._extract_timestamp(payload)

        assert extracted is not None
        assert extracted.tzinfo == timezone.utc

    def test_naive_iso_string_old_event_is_rejected(self):
        """#143: an old naive ISO timestamp must be rejected, not fail-safe-accepted.

        Previously the naive datetime caused a TypeError in ``now - event_time``
        that the broad ``except`` swallowed, returning valid=True and silently
        disabling stale-event protection.
        """
        validator = EventValidator(max_delay_seconds=60)
        # 2 minutes ago, expressed as a naive ISO string (no timezone info).
        naive_old = (datetime.now(timezone.utc) - timedelta(seconds=120)).replace(tzinfo=None)
        payload = {"timestamp": naive_old.isoformat()}

        result = validator.validate_event(payload)

        assert result.valid is False
        assert result.delay_seconds == pytest.approx(120.0, rel=1e-1)
        assert "Event too old" in result.reason
