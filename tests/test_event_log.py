"""Tests for event logging service."""

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

from nukiblinker.event_log import EventLog, EventLogEntry
from nukiblinker.event_validator import ValidationResult


class TestEventLogEntry:
    """Test cases for EventLogEntry."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        timestamp = datetime.now(timezone.utc)
        validation_result = ValidationResult(
            valid=True, delay_seconds=30.0, reason=None
        )

        entry = EventLogEntry(
            timestamp=timestamp,
            event_type="ring",
            payload={"deviceType": 2, "state": 7},
            actions=["Hue lights blinked"],
            validation_result=validation_result,
            processing_time_ms=150.5
        )

        result = entry.to_dict()

        assert result["timestamp"] == timestamp.isoformat()
        assert result["event_type"] == "ring"
        assert result["payload"] == {"deviceType": 2, "state": 7}
        assert result["actions"] == ["Hue lights blinked"]
        assert result["validation_result"]["valid"] is True
        assert result["validation_result"]["delay_seconds"] == 30.0
        assert result["validation_result"]["reason"] is None
        assert result["processing_time_ms"] == 150.5


class TestEventLog:
    """Test cases for EventLog."""

    def test_init_default(self):
        """Test EventLog initialization with default values."""
        event_log = EventLog()

        assert event_log.max_entries == 1000
        assert event_log.retention_days == 7
        assert event_log.persist_to_file is True
        assert event_log.file_path == Path("logs/event_log.json")
        assert len(event_log.entries) == 0

    def test_init_custom(self):
        """Test EventLog initialization with custom values."""
        event_log = EventLog(
            max_entries=500,
            retention_days=14,
            persist_to_file=False,
            file_path="/tmp/test_log.json"
        )

        assert event_log.max_entries == 500
        assert event_log.retention_days == 14
        assert event_log.persist_to_file is False
        assert event_log.file_path == Path("/tmp/test_log.json")

    def test_log_event(self):
        """Test basic event logging."""
        event_log = EventLog(persist_to_file=False)

        payload = {"deviceType": 2, "state": 7}
        validation_result = ValidationResult(valid=True, delay_seconds=30.0)

        event_log.log_event(
            payload=payload,
            event_type="ring",
            actions=["Hue lights blinked"],
            validation_result=validation_result,
            processing_time_ms=150.5
        )

        assert len(event_log.entries) == 1
        entry = event_log.entries[0]
        assert entry.event_type == "ring"
        assert entry.payload == payload
        assert entry.actions == ["Hue lights blinked"]
        assert entry.validation_result.valid is True
        assert entry.processing_time_ms == 150.5

    def test_get_recent_events(self):
        """Test retrieving recent events."""
        event_log = EventLog(persist_to_file=False)

        # Add 3 events
        for i in range(3):
            payload = {"deviceType": 2, "state": 7, "index": i}
            validation_result = ValidationResult(valid=True, delay_seconds=30.0)
            event_log.log_event(
                payload=payload,
                event_type="ring",
                actions=[f"Action {i}"],
                validation_result=validation_result
            )

        # Get all events (should be in reverse chronological order)
        recent = event_log.get_recent_events(limit=10)
        assert len(recent) == 3
        assert recent[0].payload["index"] == 2  # Most recent
        assert recent[1].payload["index"] == 1
        assert recent[2].payload["index"] == 0  # Oldest

    def test_get_recent_events_with_limit(self):
        """Test retrieving recent events with limit."""
        event_log = EventLog(persist_to_file=False)

        # Add 5 events
        for i in range(5):
            payload = {"deviceType": 2, "state": 7, "index": i}
            validation_result = ValidationResult(valid=True, delay_seconds=30.0)
            event_log.log_event(
                payload=payload,
                event_type="ring",
                actions=[f"Action {i}"],
                validation_result=validation_result
            )

        # Get only 3 most recent
        recent = event_log.get_recent_events(limit=3)
        assert len(recent) == 3
        assert recent[0].payload["index"] == 4
        assert recent[1].payload["index"] == 3
        assert recent[2].payload["index"] == 2

    def test_get_recent_events_with_offset(self):
        """Test retrieving recent events with offset."""
        event_log = EventLog(persist_to_file=False)

        # Add 5 events
        for i in range(5):
            payload = {"deviceType": 2, "state": 7, "index": i}
            validation_result = ValidationResult(valid=True, delay_seconds=30.0)
            event_log.log_event(
                payload=payload,
                event_type="ring",
                actions=[f"Action {i}"],
                validation_result=validation_result
            )

        # Get events with offset (skip 2 most recent)
        recent = event_log.get_recent_events(limit=10, offset=2)
        assert len(recent) == 3
        assert recent[0].payload["index"] == 2
        assert recent[1].payload["index"] == 1
        assert recent[2].payload["index"] == 0

    def test_get_event_count(self):
        """Test getting event count."""
        event_log = EventLog(persist_to_file=False)

        assert event_log.get_event_count() == 0

        # Add events
        for i in range(3):
            payload = {"deviceType": 2, "state": 7, "index": i}
            validation_result = ValidationResult(valid=True, delay_seconds=30.0)
            event_log.log_event(
                payload=payload,
                event_type="ring",
                actions=[f"Action {i}"],
                validation_result=validation_result
            )

        assert event_log.get_event_count() == 3

    def test_export_to_csv(self):
        """Test CSV export functionality."""
        event_log = EventLog(persist_to_file=False)

        # Add test events
        payload1 = {"deviceType": 2, "state": 7, "nukiId": 12345}
        payload2 = {"deviceType": 0, "state": 3, "nukiId": 67890}

        validation_result1 = ValidationResult(valid=True, delay_seconds=30.0)
        validation_result2 = ValidationResult(valid=False, delay_seconds=120.0, reason="Too old")

        event_log.log_event(
            payload=payload1,
            event_type="ring",
            actions=["Hue lights blinked", "HomeKit notification"],
            validation_result=validation_result1,
            processing_time_ms=150.5
        )

        event_log.log_event(
            payload=payload2,
            event_type="door_opened",
            actions=["Chime played"],
            validation_result=validation_result2,
            processing_time_ms=75.2
        )

        csv_content = event_log.export_to_csv()

        # Excel-friendly prefix: UTF-8 BOM + sep hint line (#96)
        assert csv_content.startswith("\ufeffsep=,\r\n")

        lines = csv_content.strip().split('\n')
        # sep hint + header + 2 data rows
        assert len(lines) == 4

        # Check header — Date/Time replace the old UTC Timestamp column (#96)
        header = lines[1]
        assert "Timestamp" not in header
        assert "Date" in header and "Time" in header
        assert "Event Type" in header
        assert "Actions" in header

        # Check data rows (newest first)
        assert "door_opened" in lines[2]
        assert "67890" in lines[2]
        assert "Chime played" in lines[2]

        assert "ring" in lines[3]
        assert "12345" in lines[3]
        assert "Hue lights blinked; HomeKit notification" in lines[3]

    def test_export_to_csv_localizes_timestamp(self):
        """#96: Date/Time columns are rendered in the configured timezone."""
        event_log = EventLog(persist_to_file=False)
        # 2026-06-12 23:30 UTC → Madrid (UTC+2 in June) = 2026-06-13 01:30
        entry = EventLogEntry(
            timestamp=datetime(2026, 6, 12, 23, 30, 0, tzinfo=timezone.utc),
            event_type="ring",
            payload={"deviceType": 2, "nukiId": 1, "state": 1},
            actions=["x"],
            validation_result=ValidationResult(valid=True, delay_seconds=0.0),
        )
        event_log.entries.append(entry)

        csv_content = event_log.export_to_csv(tz="Europe/Madrid")
        assert "2026-06-13,01:30:00" in csv_content

        # Unknown timezone falls back to UTC without raising
        utc_csv = event_log.export_to_csv(tz="Not/AZone")
        assert "2026-06-12,23:30:00" in utc_csv

    def test_export_to_csv_device_filter(self):
        """#96: export can be filtered to a single device."""
        event_log = EventLog(persist_to_file=False)
        vr = ValidationResult(valid=True, delay_seconds=0.0)
        event_log.log_event({"deviceType": 2, "nukiId": 111}, "ring", ["a"], vr)
        event_log.log_event({"deviceType": 0, "nukiId": 222}, "door_opened", ["b"], vr)

        csv_content = event_log.export_to_csv(device_id=111)
        assert "111" in csv_content
        assert "222" not in csv_content

    def test_get_devices_and_filtered_count(self):
        event_log = EventLog(persist_to_file=False)
        vr = ValidationResult(valid=True, delay_seconds=0.0)
        event_log.log_event({"deviceType": 2, "nukiId": 111, "name": "Opener"}, "ring", ["a"], vr)
        event_log.log_event({"deviceType": 2, "nukiId": 111, "name": "Opener"}, "ring", ["a"], vr)
        event_log.log_event({"deviceType": 0, "nukiId": 222, "name": "Lock"}, "door_opened", ["b"], vr)

        devices = event_log.get_devices()
        ids = {d["nukiId"] for d in devices}
        assert ids == {111, 222}

        assert event_log.get_event_count(device_id=111) == 2
        assert event_log.get_event_count(device_id=222) == 1
        assert event_log.get_event_count() == 3
        assert len(event_log.get_recent_events(device_id=111)) == 2

    def test_clear_log(self):
        """Test clearing the event log."""
        event_log = EventLog(persist_to_file=False)

        # Add an event
        payload = {"deviceType": 2, "state": 7}
        validation_result = ValidationResult(valid=True, delay_seconds=30.0)
        event_log.log_event(
            payload=payload,
            event_type="ring",
            actions=["Action"],
            validation_result=validation_result
        )

        assert len(event_log.entries) == 1

        event_log.clear_log()

        assert len(event_log.entries) == 0

    def test_cleanup_old_entries_by_retention(self):
        """Test cleanup of old entries based on retention period."""
        event_log = EventLog(retention_days=1, persist_to_file=False)

        # Add an old event (2 days ago)
        old_timestamp = datetime.now(timezone.utc) - timedelta(days=2)
        old_payload = {"deviceType": 2, "state": 7, "old": True}
        old_validation = ValidationResult(valid=True, delay_seconds=30.0)

        # Manually create old entry
        old_entry = EventLogEntry(
            timestamp=old_timestamp,
            event_type="ring",
            payload=old_payload,
            actions=["Old action"],
            validation_result=old_validation
        )
        event_log.entries.append(old_entry)

        # Add a recent event
        recent_payload = {"deviceType": 2, "state": 7, "recent": True}
        recent_validation = ValidationResult(valid=True, delay_seconds=30.0)
        event_log.log_event(
            payload=recent_payload,
            event_type="ring",
            actions=["Recent action"],
            validation_result=recent_validation
        )

        # Should have cleaned up the old entry
        assert len(event_log.entries) == 1
        assert event_log.entries[0].payload.get("recent") is True

    def test_cleanup_old_entries_by_max_entries(self):
        """Test cleanup of old entries based on max entries limit."""
        event_log = EventLog(max_entries=3, persist_to_file=False)

        # Add 5 events
        for i in range(5):
            payload = {"deviceType": 2, "state": 7, "index": i}
            validation_result = ValidationResult(valid=True, delay_seconds=30.0)
            event_log.log_event(
                payload=payload,
                event_type="ring",
                actions=[f"Action {i}"],
                validation_result=validation_result
            )

        # Should only keep the 3 most recent
        assert len(event_log.entries) == 3
        assert event_log.entries[0].payload["index"] == 2
        assert event_log.entries[1].payload["index"] == 3
        assert event_log.entries[2].payload["index"] == 4

    def test_file_persistence(self):
        """Test file persistence functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test_event_log.json"
            event_log = EventLog(
                persist_to_file=True,
                file_path=str(file_path),
                max_entries=10
            )

            # Add an event
            payload = {"deviceType": 2, "state": 7}
            validation_result = ValidationResult(valid=True, delay_seconds=30.0)
            event_log.log_event(
                payload=payload,
                event_type="ring",
                actions=["Action"],
                validation_result=validation_result
            )

            # File should be created
            assert file_path.exists()

            # Load and verify content
            with file_path.open('r') as f:
                data = json.load(f)

            assert len(data) == 1
            assert data[0]["event_type"] == "ring"
            assert data[0]["payload"] == payload

            # Create new EventLog instance and verify loading
            event_log2 = EventLog(
                persist_to_file=True,
                file_path=str(file_path),
                max_entries=10
            )

            assert len(event_log2.entries) == 1
            assert event_log2.entries[0].event_type == "ring"
            assert event_log2.entries[0].payload == payload

    def test_file_persistence_disabled(self):
        """Test that file persistence can be disabled."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test_event_log.json"
            event_log = EventLog(
                persist_to_file=False,
                file_path=str(file_path)
            )

            # Add an event
            payload = {"deviceType": 2, "state": 7}
            validation_result = ValidationResult(valid=True, delay_seconds=30.0)
            event_log.log_event(
                payload=payload,
                event_type="ring",
                actions=["Action"],
                validation_result=validation_result
            )

            # File should NOT be created
            assert not file_path.exists()

    def test_thread_safety(self):
        """Test that event logging is thread-safe."""
        import threading
        import time

        event_log = EventLog(persist_to_file=False)

        def log_events(thread_id):
            for i in range(10):
                payload = {"deviceType": 2, "state": 7, "thread": thread_id, "index": i}
                validation_result = ValidationResult(valid=True, delay_seconds=30.0)
                event_log.log_event(
                    payload=payload,
                    event_type="ring",
                    actions=[f"Action {thread_id}-{i}"],
                    validation_result=validation_result
                )
                time.sleep(0.001)  # Small delay to increase chance of race conditions

        # Create multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=log_events, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Should have all events
        assert len(event_log.entries) == 30

        # Verify no corruption
        for entry in event_log.entries:
            assert entry.event_type == "ring"
            assert isinstance(entry.payload, dict)
            assert len(entry.actions) == 1
