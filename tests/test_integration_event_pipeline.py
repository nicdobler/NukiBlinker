"""Integration tests for the complete event pipeline with new services."""

import pytest
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from nukiblinker.config import AppConfig, EventValidationConfig, NightModeConfig, EventLogConfig
from nukiblinker.event_validator import EventValidator
from nukiblinker.event_log import EventLog
from nukiblinker.night_mode import NightMode
from nukiblinker.server import _dispatch_with_logging
from nukiblinker import notifier


def _fake_datetime(hour, minute):
    """Return a datetime subclass whose now() reports the given local time.

    Subclassing keeps classmethods like combine() and today() functional.
    """
    import datetime as _dt

    class FakeDateTime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            today = _dt.date.today()
            return cls(today.year, today.month, today.day, hour, minute)

    return FakeDateTime


class TestEventPipelineIntegration:
    """Integration tests for the complete event pipeline."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration for testing."""
        config = AppConfig()

        # Enable all new features
        config.event_validation = EventValidationConfig(
            enabled=True,
            max_delay_seconds=60
        )
        config.night_mode = NightModeConfig(
            enabled=True,
            start_time="22:00",
            end_time="07:00",
            brightness_factor=0.5,
            grace_minutes=5
        )
        config.event_log = EventLogConfig(
            enabled=True,
            max_entries=100,
            retention_days=7,
            persist_to_file=False  # Disable file persistence for tests
        )

        # Configure basic services
        config.hue.bridge_ip = "192.168.1.100"
        config.hue.api_key = "test-key"
        config.hue.lights = [1, 2]

        config.nuki.bridge_ip = "192.168.1.101"
        config.nuki.api_token = "test-token"

        return config

    @pytest.fixture
    def mock_clients(self):
        """Create mock clients for testing."""
        clients = MagicMock()

        # Mock event validator
        clients.event_validator = EventValidator(max_delay_seconds=60)

        # Mock night mode
        clients.night_mode = NightMode(
            start_time="22:00",
            end_time="07:00",
            brightness_factor=0.5,
            grace_minutes=5
        )

        # Mock other clients
        clients.hue = AsyncMock()
        clients.chromecast = AsyncMock()
        clients.homekit = AsyncMock()
        clients.nuki = AsyncMock()
        clients.nuki_web = None  # Web API not configured in tests
        clients._app = None

        # Mock event log with temporary file
        with tempfile.TemporaryDirectory() as temp_dir:
            clients.event_log = EventLog(
                max_entries=100,
                persist_to_file=False,
                file_path=str(Path(temp_dir) / "test_log.json")
            )
            yield clients

    @pytest.mark.asyncio
    async def test_complete_event_pipeline_valid_event(self, mock_config, mock_clients):
        """Test complete pipeline with a valid event during daytime."""
        # Create a recent valid event
        event_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        payload = {
            "deviceType": 2,
            "nukiId": 12345,
            "state": 1,  # ring
            "timestamp": event_time.timestamp()
        }

        # Mock daytime (not night mode)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(10, 0))

            # Process the event
            validation_result = mock_clients.event_validator.validate_event(payload)
            assert validation_result.valid is True

            await _dispatch_with_logging(
                "ring", payload, mock_config, mock_clients, validation_result
            )

        # Verify event was logged
        assert len(mock_clients.event_log.entries) == 1
        logged_event = mock_clients.event_log.entries[0]
        assert logged_event.event_type == "ring"
        assert logged_event.validation_result.valid is True
        assert len(logged_event.actions) > 0

        # Verify Hue was called (not affected by night mode during day)
        mock_clients.hue.trigger_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_event_pipeline_invalid_event(self, mock_config, mock_clients):
        """Test complete pipeline with an invalid (old) event."""
        # Create an old invalid event
        event_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        payload = {
            "deviceType": 2,
            "nukiId": 12345,
            "state": 1,  # ring
            "timestamp": event_time.timestamp()
        }

        # Process the event
        validation_result = mock_clients.event_validator.validate_event(payload)
        assert validation_result.valid is False

        # Log the rejected event (simulating server behavior)
        mock_clients.event_log.log_event(
            payload=payload,
            event_type=None,
            actions=[f"Rejected: {validation_result.reason}"],
            validation_result=validation_result
        )

        # Verify event was logged as rejected
        assert len(mock_clients.event_log.entries) == 1
        logged_event = mock_clients.event_log.entries[0]
        assert logged_event.event_type is None
        assert logged_event.validation_result.valid is False
        assert "Rejected" in logged_event.actions[0]

        # Verify no notifications were sent
        mock_clients.hue.trigger_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_event_pipeline_night_mode(self, mock_config, mock_clients):
        """Test complete pipeline during night mode."""
        # Create a valid event
        event_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        payload = {
            "deviceType": 2,
            "nukiId": 12345,
            "state": 7,  # ring_to_open
            "timestamp": event_time.timestamp()
        }

        # Built-in blink still fires during night mode; only audio is disabled.
        mock_config.events.ring_to_open.blink.mode = "long"

        # Mock nighttime (night mode active)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(23, 0))

            # Process the event
            validation_result = mock_clients.event_validator.validate_event(payload)
            assert validation_result.valid is True

            await _dispatch_with_logging(
                "ring_to_open", payload, mock_config, mock_clients, validation_result
            )

        # Verify event was logged
        assert len(mock_clients.event_log.entries) == 1
        logged_event = mock_clients.event_log.entries[0]
        assert logged_event.event_type == "ring_to_open"
        assert logged_event.validation_result.valid is True

        # Verify the built-in Hue alert still fired during night mode
        mock_clients.hue.trigger_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_ring_logs_ringaction_timestamp(self, mock_config, mock_clients):
        """#204: a fresh ring is logged at its real ring time (ringactionTimestamp),
        not the callback receive time."""
        ring_ts = (datetime.now(timezone.utc) - timedelta(seconds=5)).replace(microsecond=0)
        payload = {
            "deviceType": 2, "nukiId": 12345, "state": 1,
            "ringactionState": True,
            "ringactionTimestamp": ring_ts.isoformat(),
        }
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(10, 0))
            validation_result = mock_clients.event_validator.validate_event(payload)
            assert validation_result.valid is True
            await _dispatch_with_logging(
                "ring", payload, mock_config, mock_clients, validation_result
            )

        logged = mock_clients.event_log.entries[0]
        assert logged.timestamp == ring_ts  # the real ring time, not now()

    @pytest.mark.asyncio
    async def test_ring_to_open_logs_matched_web_date(self, mock_config, mock_clients):
        """#204: a ring_to_open whose Bridge ringactionTimestamp is stale logs the
        matched Nuki Web entry date (the real open time), not the stale ts."""
        web_date = (datetime.now(timezone.utc) - timedelta(seconds=2)).replace(microsecond=0)
        mock_clients.nuki_web = AsyncMock()
        mock_clients.nuki_web.get_recent_log.return_value = [
            {"smartlockId": 12345, "name": "Nico", "trigger": 2, "source": 1,
             "date": web_date.isoformat()},
        ]
        payload = {
            "deviceType": 2, "nukiId": 12345, "state": 7,
            "ringactionState": False,
            "ringactionTimestamp": "2026-06-19T20:11:22+00:00",  # stale (yesterday)
        }
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(10, 0))
            validation_result = mock_clients.event_validator.validate_event(payload)
            await _dispatch_with_logging(
                "ring_to_open", payload, mock_config, mock_clients, validation_result
            )

        logged = mock_clients.event_log.entries[0]
        assert logged.timestamp == web_date  # matched Web date, not the stale ts

    @pytest.mark.asyncio
    async def test_event_log_persistence_and_cleanup(self, mock_config, mock_clients):
        """Test event log persistence and cleanup functionality."""
        # Create multiple events
        for i in range(5):
            event_time = datetime.now(timezone.utc) - timedelta(seconds=30 - i)
            payload = {
                "deviceType": 2,
                "nukiId": 12345,
                "state": 1,
                "timestamp": event_time.timestamp(),
                "index": i
            }

            validation_result = mock_clients.event_validator.validate_event(payload)
            mock_clients.event_log.log_event(
                payload=payload,
                event_type="ring",
                actions=[f"Action {i}"],
                validation_result=validation_result
            )

        # Verify all events were logged
        assert len(mock_clients.event_log.entries) == 5

        # Test CSV export (BOM + sep hint + header + 5 data rows) (#96)
        csv_content = mock_clients.event_log.export_to_csv()
        lines = csv_content.strip().split('\n')
        assert len(lines) == 7  # sep hint + header + 5 data rows

        # Test cleanup by max entries
        mock_clients.event_log.max_entries = 3
        mock_clients.event_log._cleanup_old_entries()
        assert len(mock_clients.event_log.entries) == 3

        # Verify newest events are kept
        entries = mock_clients.event_log.get_recent_events()
        assert entries[0].payload["index"] == 4  # Most recent
        assert entries[2].payload["index"] == 2  # Oldest kept

    @pytest.mark.asyncio
    async def test_night_mode_grace_period(self, mock_config, mock_clients):
        """Test night mode grace period functionality."""
        night_mode = NightMode(
            start_time="22:00",
            end_time="07:00",
            grace_minutes=5
        )

        # Test just before start time (within grace period)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(21, 56))
            assert night_mode.is_night_time() is True

        # Test just after end time (within grace period)
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(7, 3))
            assert night_mode.is_night_time() is True

        # Test outside grace period
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(21, 50))
            assert night_mode.is_night_time() is False

    @pytest.mark.asyncio
    async def test_event_validation_edge_cases(self, mock_config, mock_clients):
        """Test event validation edge cases."""
        validator = mock_clients.event_validator

        # Test missing timestamp
        payload_no_timestamp = {"deviceType": 2, "state": 1}
        result = validator.validate_event(payload_no_timestamp)
        assert result.valid is True
        assert result.delay_seconds == 0.0

        # Test future timestamp within grace period
        future_time = datetime.now(timezone.utc) + timedelta(minutes=1)
        payload_future = {"deviceType": 2, "state": 1, "timestamp": future_time.timestamp()}
        result = validator.validate_event(payload_future)
        assert result.valid is True
        assert result.delay_seconds < 0

        # Test future timestamp beyond grace period
        far_future_time = datetime.now(timezone.utc) + timedelta(minutes=10)
        payload_far_future = {"deviceType": 2, "state": 1, "timestamp": far_future_time.timestamp()}
        result = validator.validate_event(payload_far_future)
        assert result.valid is False
        assert "too far in the future" in result.reason

    @pytest.mark.asyncio
    async def test_notifier_with_actions_integration(self, mock_config, mock_clients):
        """Test notifier integration with action tracking."""
        from nukiblinker.config import EventRuleConfig, BlinkConfig, AudioConfig

        rule = EventRuleConfig(
            blink=BlinkConfig(mode="long"),
            audio=AudioConfig(enabled=True, mode="tts"),
            homekit=True
        )

        # HomeKit channel requires the global config flag (disabled by default)
        mock_config.homekit.enabled = True

        # Mock successful responses
        mock_clients.hue.trigger_alert.return_value = None
        mock_clients.homekit.trigger_ring.return_value = None

        actions = await notifier.notify_with_actions(rule, mock_config, mock_clients, {"name": "Test"})

        # Verify actions were returned
        assert len(actions) >= 2  # At least Hue and HomeKit
        assert any("Hue lights" in action for action in actions)
        assert any("HomeKit" in action for action in actions)

        # Verify clients were called
        mock_clients.hue.trigger_alert.assert_called_once()
        mock_clients.homekit.trigger_ring.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling_in_pipeline(self, mock_config, mock_clients):
        """Test error handling throughout the pipeline."""
        # Create a valid event
        event_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        payload = {
            "deviceType": 2,
            "nukiId": 12345,
            "state": 1,
            "timestamp": event_time.timestamp()
        }

        # Mock Hue client to raise an exception
        mock_clients.hue.trigger_alert.side_effect = Exception("Hue connection failed")

        validation_result = mock_clients.event_validator.validate_event(payload)
        assert validation_result.valid is True

        # Process the event - should handle the error gracefully
        await _dispatch_with_logging(
            "ring", payload, mock_config, mock_clients, validation_result
        )

        # Verify event was still logged despite the error
        assert len(mock_clients.event_log.entries) == 1
        logged_event = mock_clients.event_log.entries[0]
        assert logged_event.event_type == "ring"
        assert any("Error" in action for action in logged_event.actions)

    @pytest.mark.asyncio
    async def test_configuration_updates_runtime(self, mock_config, mock_clients):
        """Test that configuration updates affect runtime behavior."""
        # Initially, validation is enabled
        assert mock_config.event_validation.enabled is True

        # Create an old event that should be rejected
        old_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        payload = {
            "deviceType": 2,
            "state": 1,
            "timestamp": old_time.timestamp()
        }

        validation_result = mock_clients.event_validator.validate_event(payload)
        assert validation_result.valid is False

        # Disable validation
        mock_config.event_validation.enabled = False

        # The same event should now be processed (though validation still runs)
        # Note: In real implementation, the server checks config.event_validation.enabled
        # before rejecting events. This test verifies the validator still works.
        validation_result = mock_clients.event_validator.validate_event(payload)
        assert validation_result.valid is False  # Validator still works independently

    def test_event_log_thread_safety(self, mock_config, mock_clients):
        """Test thread safety of event logging."""
        import threading
        import time

        def log_events(thread_id):
            for i in range(10):
                payload = {"deviceType": 2, "state": 1, "thread": thread_id, "index": i}
                validation_result = mock_clients.event_validator.validate_event(payload)
                mock_clients.event_log.log_event(
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

        # Should have all events without corruption
        assert len(mock_clients.event_log.entries) == 30

        # Verify no corruption
        for entry in mock_clients.event_log.entries:
            assert entry.event_type == "ring"
            assert isinstance(entry.payload, dict)
            assert len(entry.actions) == 1


    @pytest.mark.asyncio
    async def test_nuki_web_response_stored_in_event_log(self, mock_config, mock_clients):
        """#232: a Nuki Web response used to resolve a ring is stored in the event log."""
        web_response = [
            {"smartlockId": 12345, "name": "Nico", "trigger": 2, "source": 1,
             "date": "2026-06-19T20:11:22.000Z"},
        ]
        mock_clients.nuki_web = AsyncMock()
        mock_clients.nuki_web.get_recent_log.return_value = web_response

        payload = {
            "deviceType": 2,
            "nukiId": 12345,
            "state": 1,
            "ringactionState": True,
            "ringactionTimestamp": "2026-06-19T20:11:22+00:00",
        }
        with pytest.MonkeyPatch().context() as m:
            m.setattr('nukiblinker.night_mode.datetime', _fake_datetime(10, 0))
            validation_result = mock_clients.event_validator.validate_event(payload)
            await _dispatch_with_logging(
                "ring", payload, mock_config, mock_clients, validation_result
            )

        logged = mock_clients.event_log.entries[0]
        assert logged.event_type == "ring"
        assert logged.nuki_web_response == web_response
        assert logged.to_dict()["nuki_web_response"] == web_response


# Helper function for time mocking
def time(hour, minute):
    """Create a time object for testing."""
    from datetime import time
    return time(hour, minute)
