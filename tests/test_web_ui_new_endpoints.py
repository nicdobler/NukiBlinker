"""Tests for new web UI API endpoints."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from nukiblinker.server import create_app
from nukiblinker.web_ui import mount_web_ui
from nukiblinker.config import AppConfig, EventValidationConfig, NightModeConfig, EventLogConfig
from nukiblinker.event_validator import EventValidator
from nukiblinker.event_log import EventLog
from nukiblinker.night_mode import NightMode


class TestWebUINewEndpoints:
    """Test cases for new web UI API endpoints."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration for testing."""
        config = AppConfig()

        # Configure new features
        config.event_validation = EventValidationConfig(
            enabled=True,
            max_delay_seconds=60
        )
        config.night_mode = NightModeConfig(
            enabled=True,
            start_time="22:00",
            end_time="07:00",
            brightness_factor=0.3,
            grace_minutes=5
        )
        config.event_log = EventLogConfig(
            enabled=True,
            max_entries=1000,
            retention_days=7,
            persist_to_file=False,
            file_path="logs/test_event_log.json"
        )

        return config

    @pytest.fixture
    def mock_clients(self):
        """Create mock clients for testing."""
        clients = MagicMock()

        # Mock services
        clients.event_validator = EventValidator(max_delay_seconds=60)
        clients.night_mode = NightMode(
            start_time="22:00",
            end_time="07:00",
            brightness_factor=0.3,
            grace_minutes=5
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            clients.event_log = EventLog(
                max_entries=1000,
                persist_to_file=False,
                file_path=str(Path(temp_dir) / "test_log.json")
            )
            yield clients

    @pytest.fixture
    def test_client(self, mock_config, mock_clients, tmp_path):
        """Create a test client with mock services."""
        app = create_app(mock_config, mock_clients)
        mount_web_ui(app, str(tmp_path / "config.yaml"))
        # Allow TestClient's "testclient" host through the localhost guard
        app.state.allowed_hosts = {"127.0.0.1", "::1", "localhost", "testclient"}

        return TestClient(app)

    def test_get_event_validation_config(self, test_client):
        """Test getting event validation configuration."""
        response = test_client.get("/api/config/event-validation")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["max_delay_seconds"] == 60

    def test_update_event_validation_config(self, test_client):
        """Test updating event validation configuration."""
        update_data = {
            "enabled": False,
            "max_delay_seconds": 120
        }

        response = test_client.put("/api/config/event-validation", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["max_delay_seconds"] == 120

        # Verify the service was updated
        assert test_client.app.state.clients.event_validator.max_delay_seconds == 120

    def test_update_event_validation_config_invalid(self, test_client):
        """Test updating event validation configuration with invalid data."""
        update_data = {
            "enabled": True,
            "max_delay_seconds": 5000  # Invalid: > 3600
        }

        response = test_client.put("/api/config/event-validation", json=update_data)

        assert response.status_code == 400
        assert "max_delay_seconds must be an integer between 1 and 3600" in response.json()["error"]

    def test_get_night_mode_config(self, test_client):
        """Test getting night mode configuration."""
        response = test_client.get("/api/config/night-mode")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["start_time"] == "22:00"
        assert data["end_time"] == "07:00"
        assert data["brightness_factor"] == 0.3
        assert data["grace_minutes"] == 5
        assert "status" in data

    def test_update_night_mode_config(self, test_client):
        """Test updating night mode configuration."""
        update_data = {
            "enabled": False,
            "start_time": "23:00",
            "end_time": "06:30",
            "brightness_factor": 0.5,
            "grace_minutes": 10
        }

        response = test_client.put("/api/config/night-mode", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["start_time"] == "23:00"
        assert data["end_time"] == "06:30"
        assert data["brightness_factor"] == 0.5
        assert data["grace_minutes"] == 10

    def test_update_night_mode_config_invalid_time(self, test_client):
        """Test updating night mode configuration with invalid time format."""
        update_data = {
            "enabled": True,
            "start_time": "25:00"  # Invalid time
        }

        response = test_client.put("/api/config/night-mode", json=update_data)

        assert response.status_code == 400
        assert "start_time must be in HH:MM format" in response.json()["error"]

    def test_update_night_mode_config_invalid_brightness(self, test_client):
        """Test updating night mode configuration with invalid brightness."""
        update_data = {
            "enabled": True,
            "brightness_factor": 1.5  # Invalid: > 1.0
        }

        response = test_client.put("/api/config/night-mode", json=update_data)

        assert response.status_code == 400
        assert "brightness_factor must be between 0.0 and 1.0" in response.json()["error"]

    def test_get_event_log_config(self, test_client):
        """Test getting event log configuration."""
        response = test_client.get("/api/config/event-log")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["max_entries"] == 1000
        assert data["retention_days"] == 7
        assert data["persist_to_file"] is False
        assert "stats" in data

    def test_update_event_log_config(self, test_client):
        """Test updating event log configuration."""
        update_data = {
            "enabled": False,
            "max_entries": 500,
            "retention_days": 14,
            "persist_to_file": True
        }

        response = test_client.put("/api/config/event-log", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["max_entries"] == 500
        assert data["retention_days"] == 14
        assert data["persist_to_file"] is True

    def test_update_event_log_config_invalid_entries(self, test_client):
        """Test updating event log configuration with invalid max entries."""
        update_data = {
            "enabled": True,
            "max_entries": 5  # Invalid: < 10
        }

        response = test_client.put("/api/config/event-log", json=update_data)

        assert response.status_code == 400
        assert "max_entries must be an integer between 10 and 10000" in response.json()["error"]

    def test_get_event_log_empty(self, test_client):
        """Test getting event log when empty."""
        response = test_client.get("/api/events/log")

        assert response.status_code == 200
        data = response.json()
        assert data["events"] == []
        assert data["total_count"] == 0
        assert data["limit"] == 100
        assert data["offset"] == 0

    def test_get_event_log_with_events(self, test_client, mock_clients):
        """Test getting event log with events."""
        # Add some test events
        for i in range(5):
            payload = {"deviceType": 2, "state": 1, "index": i}
            validation_result = mock_clients.event_validator.validate_event(payload)
            mock_clients.event_log.log_event(
                payload=payload,
                event_type="ring",
                actions=[f"Action {i}"],
                validation_result=validation_result
            )

        response = test_client.get("/api/events/log")

        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 5
        assert data["total_count"] == 5

        # Check event structure
        event = data["events"][0]
        assert "timestamp" in event
        assert "event_type" in event
        assert "payload" in event
        assert "actions" in event
        assert "validation_result" in event
        assert "processing_time_ms" in event

    def test_get_event_log_with_pagination(self, test_client, mock_clients):
        """Test getting event log with pagination."""
        # Add more events than default limit
        for i in range(25):
            payload = {"deviceType": 2, "state": 1, "index": i}
            validation_result = mock_clients.event_validator.validate_event(payload)
            mock_clients.event_log.log_event(
                payload=payload,
                event_type="ring",
                actions=[f"Action {i}"],
                validation_result=validation_result
            )

        # Get first page
        response = test_client.get("/api/events/log?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 10
        assert data["total_count"] == 25
        assert data["limit"] == 10
        assert data["offset"] == 0

        # Get second page
        response = test_client.get("/api/events/log?limit=10&offset=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 10
        assert data["offset"] == 10

    def test_get_event_log_disabled(self, test_client):
        """Test getting event log when disabled."""
        test_client.app.state.config.event_log.enabled = False

        response = test_client.get("/api/events/log")

        assert response.status_code == 400
        assert "Event logging is disabled" in response.json()["error"]

    def test_export_event_log(self, test_client, mock_clients):
        """Test exporting event log as CSV."""
        # Add test events
        for i in range(3):
            payload = {"deviceType": 2, "state": 1, "index": i}
            validation_result = mock_clients.event_validator.validate_event(payload)
            mock_clients.event_log.log_event(
                payload=payload,
                event_type="ring",
                actions=[f"Action {i}"],
                validation_result=validation_result
            )

        response = test_client.get("/api/events/export")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"

        # Check CSV content (BOM + sep hint + header + 3 data rows) (#96)
        csv_content = response.content.decode("utf-8-sig")
        assert csv_content.startswith("sep=,\r\n")
        lines = csv_content.strip().split('\n')
        assert len(lines) == 5  # sep hint + header + 3 data rows
        header = lines[1]
        assert "Date" in header and "Time" in header
        assert "Timestamp" not in header
        assert "Event Type" in header

    def test_export_event_log_disabled(self, test_client):
        """Test exporting event log when disabled."""
        test_client.app.state.config.event_log.enabled = False

        response = test_client.get("/api/events/export")

        assert response.status_code == 400
        assert "Event logging is disabled" in response.json()["error"]

    def test_get_event_log_devices(self, test_client, mock_clients):
        """#96: /events/devices returns the distinct devices seen."""
        vr = mock_clients.event_validator.validate_event({})
        mock_clients.event_log.log_event(
            {"deviceType": 2, "nukiId": 111, "name": "Opener"}, "ring", ["a"], vr)
        mock_clients.event_log.log_event(
            {"deviceType": 0, "nukiId": 222, "name": "Lock"}, "door_opened", ["b"], vr)

        response = test_client.get("/api/events/devices")
        assert response.status_code == 200
        ids = {d["nukiId"] for d in response.json()["devices"]}
        assert ids == {111, 222}

    def test_event_log_device_filter(self, test_client, mock_clients):
        """#96: /events/log?device_id= filters to a single device."""
        vr = mock_clients.event_validator.validate_event({})
        mock_clients.event_log.log_event(
            {"deviceType": 2, "nukiId": 111}, "ring", ["a"], vr)
        mock_clients.event_log.log_event(
            {"deviceType": 0, "nukiId": 222}, "door_opened", ["b"], vr)

        response = test_client.get("/api/events/log?device_id=111")
        assert response.status_code == 200
        data = response.json()
        assert data["device_id"] == 111
        assert data["total_count"] == 1
        assert all(e["payload"]["nukiId"] == 111 for e in data["events"])

    def test_clear_event_log(self, test_client, mock_clients):
        """Test clearing event log."""
        # Add test events
        for i in range(3):
            payload = {"deviceType": 2, "state": 1, "index": i}
            validation_result = mock_clients.event_validator.validate_event(payload)
            mock_clients.event_log.log_event(
                payload=payload,
                event_type="ring",
                actions=[f"Action {i}"],
                validation_result=validation_result
            )

        # Verify events exist
        assert len(mock_clients.event_log.entries) == 3

        # Clear log
        response = test_client.post("/api/events/clear")

        assert response.status_code == 200
        assert response.json()["status"] == "cleared"

        # Verify events are cleared
        assert len(mock_clients.event_log.entries) == 0

    def test_clear_event_log_disabled(self, test_client):
        """Test clearing event log when disabled."""
        test_client.app.state.config.event_log.enabled = False

        response = test_client.post("/api/events/clear")

        assert response.status_code == 400
        assert "Event logging is disabled" in response.json()["error"]

    def test_event_log_entry_serialization(self, test_client, mock_clients):
        """Test that event log entries are properly serialized."""
        # Create an event with all fields
        payload = {"deviceType": 2, "state": 1, "test": True}
        validation_result = mock_clients.event_validator.validate_event(payload)

        mock_clients.event_log.log_event(
            payload=payload,
            event_type="ring",
            actions=["Hue lights blinked", "Audio played"],
            validation_result=validation_result,
            processing_time_ms=150.5
        )

        response = test_client.get("/api/events/log")

        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 1

        event = data["events"][0]
        assert event["event_type"] == "ring"
        assert event["payload"]["test"] is True
        assert len(event["actions"]) == 2
        assert "Hue lights blinked" in event["actions"]
        assert "Audio played" in event["actions"]
        assert event["validation_result"]["valid"] is True
        assert event["processing_time_ms"] == 150.5
        assert "timestamp" in event

    def test_night_mode_status_in_config(self, test_client, mock_clients):
        """Test that night mode status is included in config response."""
        # Mock current time as nighttime (23:00). A datetime subclass keeps
        # classmethods like combine()/today() functional.
        import datetime as _dt

        class FakeDateTime(_dt.datetime):
            @classmethod
            def now(cls, tz=None):
                t = _dt.date.today()
                return cls(t.year, t.month, t.day, 23, 0)

        with patch('nukiblinker.night_mode.datetime', FakeDateTime):
            response = test_client.get("/api/config/night-mode")

            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert data["status"]["enabled"] is True
            assert data["status"]["active"] is True

    def test_event_log_stats_in_config(self, test_client, mock_clients):
        """Test that event log statistics are included in config response."""
        # Add some events
        for i in range(5):
            payload = {"deviceType": 2, "state": 1, "index": i}
            validation_result = mock_clients.event_validator.validate_event(payload)
            mock_clients.event_log.log_event(
                payload=payload,
                event_type="ring",
                actions=[f"Action {i}"],
                validation_result=validation_result
            )

        response = test_client.get("/api/config/event-log")

        assert response.status_code == 200
        data = response.json()
        assert "stats" in data
        assert data["stats"]["current_entries"] == 5
        assert data["stats"]["max_entries"] == 1000
        assert data["stats"]["retention_days"] == 7

    def test_config_update_persistence(self, test_client, mock_clients):
        """Test that configuration updates are properly persisted."""
        # Update event validation config
        update_data = {"enabled": False, "max_delay_seconds": 120}
        response = test_client.put("/api/config/event-validation", json=update_data)
        assert response.status_code == 200

        # Update night mode config
        update_data = {"enabled": True, "brightness_factor": 0.7}
        response = test_client.put("/api/config/night-mode", json=update_data)
        assert response.status_code == 200

        # Update event log config
        update_data = {"enabled": True, "max_entries": 500}
        response = test_client.put("/api/config/event-log", json=update_data)
        assert response.status_code == 200

        # Verify all updates were applied
        assert test_client.app.state.config.event_validation.enabled is False
        assert test_client.app.state.config.event_validation.max_delay_seconds == 120
        assert test_client.app.state.config.night_mode.brightness_factor == 0.7
        assert test_client.app.state.config.event_log.max_entries == 500

    def test_error_handling_invalid_json(self, test_client):
        """Test error handling for invalid JSON in configuration updates."""
        response = test_client.put(
            "/api/config/event-validation",
            data="invalid json",
            headers={"content-type": "application/json"}
        )

        assert response.status_code == 400  # Bad Request: malformed JSON

    def test_concurrent_event_log_access(self, test_client, mock_clients):
        """Test concurrent access to event log endpoints."""
        import threading
        import time

        def add_events():
            for i in range(10):
                payload = {"deviceType": 2, "state": 1, "thread": i}
                validation_result = mock_clients.event_validator.validate_event(payload)
                mock_clients.event_log.log_event(
                    payload=payload,
                    event_type="ring",
                    actions=[f"Action {i}"],
                    validation_result=validation_result
                )

        def read_events():
            for _ in range(5):
                response = test_client.get("/api/events/log")
                assert response.status_code == 200
                time.sleep(0.001)

        # Start concurrent operations
        threads = []
        for i in range(2):
            writer = threading.Thread(target=add_events)
            reader = threading.Thread(target=read_events)
            threads.extend([writer, reader])

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Verify all events were added
        response = test_client.get("/api/events/log")
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 20
