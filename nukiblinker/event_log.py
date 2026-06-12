"""Event logging service.

Provides persistent event logging with web UI access for troubleshooting
and monitoring Nuki event processing.
"""

import json
import logging
import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
from threading import Lock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .event_validator import ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class EventLogEntry:
    """Single event log entry."""
    timestamp: datetime
    event_type: Optional[str]  # "ring", "ring_to_open", "door_opened", or None if unknown
    payload: Dict[str, Any]
    actions: List[str]  # List of actions taken (e.g., ["Hue lights blinked", "TTS played"])
    validation_result: ValidationResult
    processing_time_ms: Optional[float] = None  # Time taken to process the event

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "payload": self.payload,
            "actions": self.actions,
            "validation_result": {
                "valid": self.validation_result.valid,
                "delay_seconds": self.validation_result.delay_seconds,
                "reason": self.validation_result.reason
            },
            "processing_time_ms": self.processing_time_ms
        }


class EventLog:
    """Persistent event logging with web UI access."""

    def __init__(self, max_entries: int = 1000, retention_days: int = 7,
                 persist_to_file: bool = True, file_path: str = "logs/event_log.json"):
        """Initialize event log.

        Args:
            max_entries: Maximum number of entries to keep in memory
            retention_days: How long to keep entries (default 7 days)
            persist_to_file: Whether to persist log to file
            file_path: Path to persistence file
        """
        self.max_entries = max_entries
        self.retention_days = retention_days
        self.persist_to_file = persist_to_file
        self.file_path = Path(file_path)
        self.entries: List[EventLogEntry] = []
        self._lock = Lock()

        # Ensure log directory exists
        if self.persist_to_file:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_file()

        logger.info(
                "EventLog initialized: max_entries=%d, retention_days=%d, persist=%s",
                max_entries, retention_days, persist_to_file
            )

    def log_event(self, payload: Dict[str, Any], event_type: Optional[str],
                  actions: List[str], validation_result: ValidationResult,
                  processing_time_ms: Optional[float] = None):
        """Add event to log with full context.

        Args:
            payload: Original Nuki callback payload
            event_type: Classified event type
            actions: List of actions taken
            validation_result: Result of event validation
            processing_time_ms: Time taken to process the event
        """
        entry = EventLogEntry(
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            payload=payload,
            actions=actions,
            validation_result=validation_result,
            processing_time_ms=processing_time_ms
        )

        with self._lock:
            self.entries.append(entry)
            self._cleanup_old_entries()

            if self.persist_to_file:
                self._save_to_file()

        logger.debug(
                "Event logged: type=%s, actions=%d, valid=%s",
                event_type, len(actions), validation_result.valid
            )

    def get_recent_events(self, limit: int = 100, offset: int = 0,
                          device_id: Optional[int] = None) -> List[EventLogEntry]:
        """Return recent events for web UI.

        Args:
            limit: Maximum number of entries to return
            offset: Number of entries to skip (for pagination)
            device_id: Optional nukiId to filter by

        Returns:
            List of event log entries
        """
        with self._lock:
            # Return entries in reverse chronological order (newest first)
            items = list(reversed(self.entries))
        if device_id is not None:
            items = [e for e in items if e.payload.get("nukiId") == device_id]
        return items[offset:offset + limit]

    def get_event_count(self, device_id: Optional[int] = None) -> int:
        """Get total number of events in log (optionally filtered by device)."""
        with self._lock:
            if device_id is None:
                return len(self.entries)
            return sum(1 for e in self.entries if e.payload.get("nukiId") == device_id)

    def get_devices(self) -> List[Dict[str, Any]]:
        """Return the distinct devices seen in the log (for the UI filter).

        Returns:
            List of {"nukiId", "deviceType", "name"} dicts, newest-seen first.
        """
        with self._lock:
            entries = list(reversed(self.entries))
        devices: Dict[Any, Dict[str, Any]] = {}
        for entry in entries:
            nuki_id = entry.payload.get("nukiId")
            if nuki_id is None or nuki_id in devices:
                continue
            devices[nuki_id] = {
                "nukiId": nuki_id,
                "deviceType": entry.payload.get("deviceType"),
                "name": entry.payload.get("name"),
            }
        return list(devices.values())

    def export_to_csv(self, device_id: Optional[int] = None,
                      tz: str = "Europe/Madrid") -> str:
        """Export event log to CSV format.

        The output is Excel-friendly: it starts with a UTF-8 BOM and an Excel
        ``sep=,`` hint line so columns and accented characters render correctly
        even in locales (e.g. Spanish) where Excel defaults to ``;`` separators.
        Timestamps are converted to the given timezone and split into separate
        Date (YYYY-MM-DD) and Time (HH:MM:SS) columns (#96).

        Args:
            device_id: Optional nukiId to filter rows by.
            tz: IANA timezone name for the Date/Time columns.

        Returns:
            CSV string (prefixed with BOM + ``sep=,`` hint).
        """
        try:
            zone = ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            logger.warning("Unknown timezone %r for CSV export — using UTC", tz)
            zone = timezone.utc

        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            "Date", "Time", "Event Type", "Device Type", "Device ID",
            "Device Name", "State", "Validation Valid", "Validation Delay (s)",
            "Validation Reason", "Actions", "Processing Time (ms)"
        ])

        with self._lock:
            entries = list(reversed(self.entries))  # Newest first

        for entry in entries:
            if device_id is not None and entry.payload.get("nukiId") != device_id:
                continue

            local_ts = entry.timestamp.astimezone(zone)

            writer.writerow([
                local_ts.strftime("%Y-%m-%d"),
                local_ts.strftime("%H:%M:%S"),
                entry.event_type or "Unknown",
                entry.payload.get("deviceType"),
                entry.payload.get("nukiId"),
                entry.payload.get("name") or "",
                entry.payload.get("state"),
                entry.validation_result.valid,
                f"{entry.validation_result.delay_seconds:.2f}",
                entry.validation_result.reason or "",
                "; ".join(entry.actions),
                f"{entry.processing_time_ms:.2f}" if entry.processing_time_ms else ""
            ])

        # BOM + Excel separator hint so Excel (incl. ES locale) parses columns.
        return "\ufeff" + "sep=,\r\n" + output.getvalue()

    def clear_log(self):
        """Clear all events from log."""
        with self._lock:
            self.entries.clear()
            if self.persist_to_file and self.file_path.exists():
                self.file_path.unlink()

        logger.info("Event log cleared")

    def _cleanup_old_entries(self):
        """Remove entries older than retention period."""
        if not self.retention_days:
            return

        cutoff_time = datetime.now(timezone.utc) - timedelta(days=self.retention_days)

        # Remove old entries
        original_count = len(self.entries)
        self.entries = [entry for entry in self.entries if entry.timestamp > cutoff_time]

        # Also enforce max entries limit
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

        removed_count = original_count - len(self.entries)
        if removed_count > 0:
            logger.debug("Cleaned up %d old event log entries", removed_count)

    def _save_to_file(self):
        """Save event log to file."""
        try:
            # Only save the most recent entries to avoid huge files
            entries_to_save = self.entries[-self.max_entries:]
            data = [entry.to_dict() for entry in entries_to_save]

            # Write to temporary file first, then rename to avoid corruption
            temp_file = self.file_path.with_suffix('.tmp')
            with temp_file.open('w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            temp_file.rename(self.file_path)

        except Exception as e:
            logger.error("Failed to save event log to file %s: %s", self.file_path, e)

    def _load_from_file(self):
        """Load event log from file."""
        if not self.file_path.exists():
            return

        try:
            with self.file_path.open('r', encoding='utf-8') as f:
                data = json.load(f)

            entries = []
            for entry_data in data:
                try:
                    # Reconstruct ValidationResult
                    vr_data = entry_data["validation_result"]
                    validation_result = ValidationResult(
                        valid=vr_data["valid"],
                        delay_seconds=vr_data["delay_seconds"],
                        reason=vr_data.get("reason")
                    )

                    # Reconstruct EventLogEntry
                    entry = EventLogEntry(
                        timestamp=datetime.fromisoformat(entry_data["timestamp"]),
                        event_type=entry_data.get("event_type"),
                        payload=entry_data["payload"],
                        actions=entry_data["actions"],
                        validation_result=validation_result,
                        processing_time_ms=entry_data.get("processing_time_ms")
                    )
                    entries.append(entry)

                except Exception as e:
                    logger.warning("Failed to load event log entry: %s", e)
                    continue

            self.entries = entries
            logger.info("Loaded %d event log entries from file", len(entries))

        except Exception as e:
            logger.error("Failed to load event log from file %s: %s", self.file_path, e)
