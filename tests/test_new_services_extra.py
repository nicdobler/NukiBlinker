"""Extra coverage tests for EventValidator, NightMode and EventLog.

All tests are based strictly on the public APIs of the new services.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from nukiblinker.config import EventRuleConfig
from nukiblinker.event_log import EventLog, EventLogEntry
from nukiblinker.event_validator import EventValidator, ValidationResult
from nukiblinker.night_mode import NightMode


class TestEventValidatorExtra:
    def test_empty_payload_is_valid(self):
        validator = EventValidator(max_delay_seconds=60)
        result = validator.validate_event({})
        assert result.valid is True
        assert result.delay_seconds == 0.0
        assert result.reason is None

    def test_unparseable_timestamp_is_valid(self):
        validator = EventValidator(max_delay_seconds=60)
        result = validator.validate_event({"timestamp": "not-a-date"})
        assert result.valid is True

    def test_old_event_rejected(self):
        validator = EventValidator(max_delay_seconds=60)
        old = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()
        result = validator.validate_event({"timestamp": old})
        assert result.valid is False
        assert "Event too old" in result.reason

    def test_recent_event_accepted(self):
        validator = EventValidator(max_delay_seconds=60)
        recent = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        result = validator.validate_event({"timestamp": recent})
        assert result.valid is True
        assert result.reason is None

    def test_far_future_event_rejected(self):
        validator = EventValidator(max_delay_seconds=60)
        future = (datetime.now(timezone.utc) + timedelta(seconds=600)).isoformat()
        result = validator.validate_event({"timestamp": future})
        assert result.valid is False
        assert "future" in result.reason

    def test_near_future_event_accepted(self):
        validator = EventValidator(max_delay_seconds=60)
        future = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
        result = validator.validate_event({"timestamp": future})
        assert result.valid is True

    def test_unix_seconds_timestamp(self):
        validator = EventValidator(max_delay_seconds=60)
        ts = datetime.now(timezone.utc).timestamp()
        result = validator.validate_event({"timestamp": ts})
        assert result.valid is True

    def test_unix_milliseconds_timestamp(self):
        validator = EventValidator(max_delay_seconds=60)
        ts_ms = datetime.now(timezone.utc).timestamp() * 1000
        result = validator.validate_event({"timestamp": ts_ms})
        assert result.valid is True

    def test_unix_string_timestamp(self):
        validator = EventValidator(max_delay_seconds=60)
        ts = str(datetime.now(timezone.utc).timestamp())
        result = validator.validate_event({"timestamp": ts})
        assert result.valid is True

    @pytest.mark.parametrize("field", ["time", "created_at", "eventTime"])
    def test_alternative_timestamp_fields(self, field):
        validator = EventValidator(max_delay_seconds=60)
        recent = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        result = validator.validate_event({field: recent})
        assert result.valid is True

    def test_parse_timestamp_value_rejects_unsupported_type(self):
        validator = EventValidator(max_delay_seconds=60)
        with pytest.raises(ValueError):
            validator._parse_timestamp_value([])

    def test_none_payload_fail_safe(self):
        validator = EventValidator(max_delay_seconds=60)
        result = validator.validate_event(None)
        assert result.valid is True
        assert result.reason is not None
        assert result.reason.startswith("Validation error")


class TestNightModeExtra:
    def test_invalid_times_disable_night_mode(self):
        nm = NightMode(start_time="invalid", end_time="07:00")
        assert nm.is_enabled() is False
        assert nm.is_night_time() is False
        assert nm.get_next_change_time() is None

    def test_invalid_hour_disables_night_mode(self):
        nm = NightMode(start_time="25:00", end_time="07:00")
        assert nm.is_enabled() is False

    def test_valid_configuration_enabled(self):
        nm = NightMode(start_time="22:00", end_time="07:00", brightness_factor=0.5, grace_minutes=5)
        assert nm.is_enabled() is True
        assert isinstance(nm.is_night_time(), bool)
        assert nm.get_next_change_time() is not None

    def test_brightness_factor_clamped(self):
        nm = NightMode(start_time="22:00", end_time="07:00", brightness_factor=5.0)
        assert nm.brightness_factor == 1.0
        nm = NightMode(start_time="22:00", end_time="07:00", brightness_factor=-1.0)
        assert nm.brightness_factor == 0.0

    def test_get_status_returns_dict(self):
        nm = NightMode(start_time="22:00", end_time="07:00")
        status = nm.get_status()
        assert isinstance(status, dict)

    def test_update_settings(self):
        nm = NightMode(start_time="22:00", end_time="07:00")
        nm.update_settings(start_time="23:00", end_time="06:00", brightness_factor=0.2, grace_minutes=10)
        assert nm.start_time_str == "23:00"
        assert nm.end_time_str == "06:00"
        assert nm.brightness_factor == 0.2
        assert nm.grace_minutes == 10

    def test_apply_night_mode_outside_night_returns_rule(self):
        nm = NightMode(start_time="invalid", end_time="invalid")
        rule = EventRuleConfig()
        assert nm.apply_night_mode(rule) is rule

    def test_apply_night_mode_disables_audio_during_night(self):
        nm = NightMode(start_time="22:00", end_time="23:00", grace_minutes=0)
        rule = EventRuleConfig()
        with patch("nukiblinker.night_mode.datetime") as mock_dt:
            from datetime import datetime as real_datetime
            mock_dt.now.return_value = real_datetime(2026, 1, 1, 22, 30, 0)
            mock_dt.combine = real_datetime.combine
            mock_dt.today = real_datetime.today
            assert nm.is_night_time() is True
            night_rule = nm.apply_night_mode(rule)
        assert night_rule.audio.enabled is False


class TestEventLogExtra:
    def _make_result(self):
        return ValidationResult(valid=True, delay_seconds=1.0)

    def test_max_entries_enforced(self):
        log = EventLog(max_entries=5, retention_days=7, persist_to_file=False)
        for i in range(10):
            log.log_event(
                payload={"deviceType": 2, "state": 1, "index": i},
                event_type="ring",
                actions=[f"action-{i}"],
                validation_result=self._make_result(),
            )
        assert log.get_event_count() == 5

    def test_get_recent_events_newest_first(self):
        log = EventLog(max_entries=100, persist_to_file=False)
        for i in range(5):
            log.log_event(
                payload={"index": i},
                event_type="ring",
                actions=[],
                validation_result=self._make_result(),
            )
        events = log.get_recent_events(limit=3)
        assert len(events) == 3
        assert events[0].payload["index"] == 4

    def test_export_to_csv(self):
        log = EventLog(max_entries=10, persist_to_file=False)
        log.log_event(
            payload={"deviceType": 2, "nukiId": 123, "state": 1},
            event_type="ring",
            actions=["Hue lights blinked"],
            validation_result=self._make_result(),
            processing_time_ms=12.5,
        )
        csv_content = log.export_to_csv()
        assert "Timestamp" in csv_content
        assert "ring" in csv_content
        assert "Hue lights blinked" in csv_content

    def test_export_to_csv_empty_log(self):
        log = EventLog(max_entries=10, persist_to_file=False)
        csv_content = log.export_to_csv()
        assert "Timestamp" in csv_content

    def test_clear_log(self):
        log = EventLog(max_entries=10, persist_to_file=False)
        log.log_event(
            payload={},
            event_type="ring",
            actions=[],
            validation_result=self._make_result(),
        )
        assert log.get_event_count() == 1
        log.clear_log()
        assert log.get_event_count() == 0

    def test_entry_to_dict(self):
        entry = EventLogEntry(
            timestamp=datetime.now(timezone.utc),
            event_type="ring",
            payload={"key": "value"},
            actions=["a1"],
            validation_result=ValidationResult(valid=True, delay_seconds=2.0, reason=None),
            processing_time_ms=42.0,
        )
        data = entry.to_dict()
        assert data["event_type"] == "ring"
        assert data["payload"] == {"key": "value"}
        assert data["actions"] == ["a1"]
        assert data["validation_result"]["valid"] is True
        assert data["validation_result"]["delay_seconds"] == 2.0
        assert data["processing_time_ms"] == 42.0

    def test_persistence_roundtrip(self, tmp_path):
        file_path = tmp_path / "events.json"
        log = EventLog(max_entries=10, persist_to_file=True, file_path=str(file_path))
        log.log_event(
            payload={"deviceType": 2},
            event_type="ring",
            actions=["played"],
            validation_result=self._make_result(),
        )
        assert file_path.exists()

        reloaded = EventLog(max_entries=10, persist_to_file=True, file_path=str(file_path))
        assert reloaded.get_event_count() == 1
        assert reloaded.entries[0].event_type == "ring"

    def test_retention_cleanup(self):
        log = EventLog(max_entries=100, retention_days=1, persist_to_file=False)
        old_entry = EventLogEntry(
            timestamp=datetime.now(timezone.utc) - timedelta(days=2),
            event_type="old",
            payload={},
            actions=[],
            validation_result=self._make_result(),
        )
        log.entries.append(old_entry)
        log.log_event(
            payload={},
            event_type="recent",
            actions=[],
            validation_result=self._make_result(),
        )
        assert log.get_event_count() == 1
        assert log.entries[0].event_type == "recent"
