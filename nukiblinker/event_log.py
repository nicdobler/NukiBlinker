"""Event logging service.

Provides persistent event logging with web UI access for troubleshooting
and monitoring Nuki event processing.

The log is persisted in an embedded SQLite database (stdlib ``sqlite3`` — no
extra dependency or container). Each event is a single ``INSERT`` and the web UI
reads events with indexed, paginated queries, so the log no longer rewrites a
whole JSON file on every event nor loses its history between application versions
(provided the DB file lives on a mounted volume).
"""

import json
import logging
import csv
import io
import sqlite3
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
    nuki_web_response: Optional[List[Dict[str, Any]]] = None  # Raw Nuki Web API response (#232)

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
            "processing_time_ms": self.processing_time_ms,
            "nuki_web_response": self.nuki_web_response,
        }


_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    nuki_id INTEGER,
    device_type INTEGER,
    device_name TEXT,
    event_type TEXT,
    payload TEXT NOT NULL,
    actions TEXT NOT NULL,
    valid INTEGER NOT NULL,
    delay_seconds REAL,
    reason TEXT,
    processing_time_ms REAL,
    nuki_web_response TEXT
);
"""


class EventLog:
    """Persistent event logging with web UI access, backed by SQLite."""

    def __init__(self, max_entries: int = 1000, retention_days: int = 7,
                 persist_to_file: bool = True, file_path: str = "logs/event_log.db"):
        """Initialize event log.

        Args:
            max_entries: Maximum number of entries to keep
            retention_days: How long to keep entries (default 7 days)
            persist_to_file: Whether to persist to an on-disk SQLite DB. When
                False, an in-memory (``:memory:``) database is used.
            file_path: Path to the SQLite database file. A legacy ``.json`` path
                is transparently mapped to a sibling ``.db`` (and the old JSON is
                migrated on first start), so existing configs keep working.
        """
        self.max_entries = max_entries
        self.retention_days = retention_days
        self.persist_to_file = persist_to_file
        # Preserve the configured path for back-compat (web UI echoes it).
        self.file_path = Path(file_path)
        self._lock = Lock()
        self._legacy_json_path: Optional[Path] = None

        if self.persist_to_file:
            if self.file_path.suffix.lower() == ".json":
                # Map a legacy JSON path to a clean sibling .db file.
                self.db_path: Optional[Path] = self.file_path.with_name(
                    self.file_path.stem + ".db"
                )
                self._legacy_json_path = self.file_path
            else:
                self.db_path = self.file_path
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
        else:
            self.db_path = None
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)

        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_nuki_id ON events(nuki_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
        self._migrate_db()
        self._conn.commit()

        if self.persist_to_file and self._legacy_json_path is not None:
            self._migrate_legacy_json()

        logger.info(
            "EventLog initialized: backend=sqlite, db=%s, max_entries=%d, "
            "retention_days=%d, persist=%s",
            self.db_path if self.db_path is not None else ":memory:",
            max_entries, retention_days, persist_to_file
        )

    @property
    def entries(self) -> List[EventLogEntry]:
        """Back-compat read accessor: all rows in chronological (oldest-first) order."""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM events ORDER BY id ASC").fetchall()
        return [self._row_to_entry(row) for row in rows]

    def close(self):
        """Close the underlying SQLite connection."""
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass

    def store_entry(self, entry: EventLogEntry):
        """Insert a pre-built entry and enforce retention/max-entries.

        Used by ``log_event``, the legacy-JSON migration, and tests that need a
        custom timestamp.
        """
        with self._lock:
            self._insert_entry(entry)
            self._cleanup_old_entries_locked()
            self._conn.commit()

    def log_event(self, payload: Dict[str, Any], event_type: Optional[str],
                  actions: List[str], validation_result: ValidationResult,
                  processing_time_ms: Optional[float] = None,
                  event_time: Optional[datetime] = None,
                  nuki_web_response: Optional[List[Dict[str, Any]]] = None):
        """Add event to log with full context.

        Args:
            payload: Original Nuki callback payload
            event_type: Classified event type
            actions: List of actions taken
            validation_result: Result of event validation
            processing_time_ms: Time taken to process the event
            event_time: The real time the action happened (#204). When None,
                defaults to ``datetime.now(UTC)`` (the callback receive time) so
                existing callers keep working. Naive values are treated as UTC.
                Callers derive it via ``event_router.event_time_for_log``.
            nuki_web_response: Raw Nuki Web API response (recent log entries) used
                for name/trigger resolution (#232). When None, no Web API call was
                made for this event.
        """
        if event_time is None:
            event_time = datetime.now(timezone.utc)
        elif event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        entry = EventLogEntry(
            timestamp=event_time,
            event_type=event_type,
            payload=payload,
            actions=actions,
            validation_result=validation_result,
            processing_time_ms=processing_time_ms,
            nuki_web_response=nuki_web_response,
        )

        self.store_entry(entry)

        logger.debug(
                "Event logged: type=%s, actions=%d, valid=%s",
                event_type, len(actions), validation_result.valid
            )

    def _migrate_db(self):
        """Add any missing columns to an existing SQLite DB.

        New `EventLog` fields need to be present on pre-existing DB files without
        requiring a manual rebuild. The table is created by ``_SCHEMA`` on fresh
        files, so this only needs to add columns that are missing from older
        deployments.
        """
        existing = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(events)")
        }
        if "nuki_web_response" not in existing:
            self._conn.execute(
                "ALTER TABLE events ADD COLUMN nuki_web_response TEXT"
            )

    def _insert_entry(self, entry: EventLogEntry):
        """Insert one entry. Caller must hold ``self._lock``."""
        payload = entry.payload or {}
        ts = entry.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        self._conn.execute(
            "INSERT INTO events (timestamp, nuki_id, device_type, device_name, "
            "event_type, payload, actions, valid, delay_seconds, reason, "
            "processing_time_ms, nuki_web_response) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts.astimezone(timezone.utc).isoformat(),
                payload.get("nukiId"),
                payload.get("deviceType"),
                payload.get("name"),
                entry.event_type,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(entry.actions, ensure_ascii=False),
                1 if entry.validation_result.valid else 0,
                entry.validation_result.delay_seconds,
                entry.validation_result.reason,
                entry.processing_time_ms,
                json.dumps(entry.nuki_web_response, ensure_ascii=False)
                if entry.nuki_web_response is not None
                else None,
            ),
        )

    def _row_to_entry(self, row: sqlite3.Row) -> EventLogEntry:
        """Reconstruct an EventLogEntry from a DB row."""
        validation_result = ValidationResult(
            valid=bool(row["valid"]),
            delay_seconds=row["delay_seconds"],
            reason=row["reason"],
        )
        return EventLogEntry(
            timestamp=datetime.fromisoformat(row["timestamp"]),
            event_type=row["event_type"],
            payload=json.loads(row["payload"]),
            actions=json.loads(row["actions"]),
            validation_result=validation_result,
            processing_time_ms=row["processing_time_ms"],
            nuki_web_response=(
                json.loads(row["nuki_web_response"])
                if row["nuki_web_response"] is not None
                else None
            ),
        )

    def _migrate_legacy_json(self):
        """Import a legacy JSON event log into the SQLite DB (one-time)."""
        legacy = self._legacy_json_path
        if legacy is None or not legacy.exists():
            return

        with self._lock:
            count = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        if count:
            return  # DB already populated — don't double-import

        try:
            with legacy.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            logger.warning(
                "Legacy event log %s is not valid JSON, skipping migration: %s",
                legacy, e
            )
            return

        migrated = 0
        with self._lock:
            for item in data:
                try:
                    vr = item["validation_result"]
                    entry = EventLogEntry(
                        timestamp=datetime.fromisoformat(item["timestamp"]),
                        event_type=item.get("event_type"),
                        payload=item["payload"],
                        actions=item["actions"],
                        validation_result=ValidationResult(
                            valid=vr["valid"],
                            delay_seconds=vr["delay_seconds"],
                            reason=vr.get("reason"),
                        ),
                        processing_time_ms=item.get("processing_time_ms"),
                    )
                    self._insert_entry(entry)
                    migrated += 1
                except (KeyError, ValueError, TypeError) as e:
                    logger.warning("Failed to migrate a legacy event log entry: %s", e)
            self._cleanup_old_entries_locked()
            self._conn.commit()

        try:
            legacy.rename(legacy.parent / (legacy.name + ".migrated"))
        except OSError as e:
            logger.warning("Could not rename migrated legacy log %s: %s", legacy, e)

        logger.info(
            "Migrated %d entries from legacy JSON event log %s", migrated, legacy
        )

    @staticmethod
    def _build_filters(device_id: Optional[int] = None,
                       actions_only: bool = False) -> tuple[str, list]:
        """Build a shared SQL WHERE clause for the event filters.

        Returns a ``(clause, params)`` tuple where ``clause`` is empty or starts
        with ``" WHERE "``. ``actions_only`` keeps only events that triggered at
        least one action (the ``actions`` column is a JSON array, empty ``"[]"``
        when no action ran).
        """
        conditions: List[str] = []
        params: list = []
        if device_id is not None:
            conditions.append("nuki_id = ?")
            params.append(device_id)
        if actions_only:
            conditions.append("actions IS NOT NULL AND actions != '[]'")
        clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        return clause, params

    def get_recent_events(self, limit: int = 100, offset: int = 0,
                          device_id: Optional[int] = None,
                          actions_only: bool = False) -> List[EventLogEntry]:
        """Return recent events for web UI.

        Args:
            limit: Maximum number of entries to return
            offset: Number of entries to skip (for pagination)
            device_id: Optional nukiId to filter by
            actions_only: When True, only return events that triggered actions

        Returns:
            List of event log entries, newest first.
        """
        clause, params = self._build_filters(device_id, actions_only)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM events{clause} ORDER BY id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get_events_in_range(self, start: datetime, end: datetime) -> List[EventLogEntry]:
        """Return events whose timestamp falls within ``[start, end]`` (#117).

        Bounds may be naive or aware; naive values are treated as UTC. Stored
        timestamps are UTC ISO strings, so both bounds are normalised to UTC
        for the comparison. Results are ordered oldest-first (chronological),
        which reads naturally in a support bundle.
        """
        def _utc_iso(dt: datetime) -> str:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()

        start_iso, end_iso = _utc_iso(start), _utc_iso(end)
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE timestamp BETWEEN ? AND ? "
                "ORDER BY timestamp ASC",
                (start_iso, end_iso),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    @staticmethod
    def _utc_iso(dt: datetime) -> str:
        """Normalise a (possibly naive) datetime to a UTC ISO string."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    def get_previous_event(self, before: datetime) -> Optional[EventLogEntry]:
        """Return the most recent event strictly *before* ``before`` (#224).

        Used to bound a support bundle's window at the end of the preceding
        event. Returns ``None`` when the given time is at/before the first
        recorded event.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM events WHERE timestamp < ? ORDER BY timestamp DESC LIMIT 1",
                (self._utc_iso(before),),
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def get_next_event(self, after: datetime) -> Optional[EventLogEntry]:
        """Return the earliest event strictly *after* ``after`` (#224).

        Used to bound a support bundle's window at the start of the following
        event. Returns ``None`` when the given time is at/after the last
        recorded event.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM events WHERE timestamp > ? ORDER BY timestamp ASC LIMIT 1",
                (self._utc_iso(after),),
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def get_event_count(self, device_id: Optional[int] = None,
                        actions_only: bool = False) -> int:
        """Get total number of events in log (optionally filtered).

        Args:
            device_id: Optional nukiId to filter by.
            actions_only: When True, only count events that triggered actions.
        """
        clause, params = self._build_filters(device_id, actions_only)
        with self._lock:
            row = self._conn.execute(
                f"SELECT COUNT(*) FROM events{clause}", params
            ).fetchone()
        return row[0]

    def get_devices(self) -> List[Dict[str, Any]]:
        """Return the distinct devices seen in the log (for the UI filter).

        Returns:
            List of {"nukiId", "deviceType", "name"} dicts, newest-seen first.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT nuki_id, device_type, device_name, MAX(id) AS last_id "
                "FROM events WHERE nuki_id IS NOT NULL "
                "GROUP BY nuki_id ORDER BY last_id DESC"
            ).fetchall()
        return [
            {
                "nukiId": row["nuki_id"],
                "deviceType": row["device_type"],
                "name": row["device_name"],
            }
            for row in rows
        ]

    def export_to_csv(self, device_id: Optional[int] = None,
                      tz: str = "Europe/Madrid",
                      device_names: Optional[Dict[int, str]] = None) -> str:
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

        names = device_names or {}
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            "Date", "Time", "Event Type", "Device Type", "Device ID",
            "Device Name", "State", "Validation Valid", "Validation Delay (s)",
            "Validation Reason", "Actions", "Processing Time (ms)", "Payload (JSON)"
        ])

        with self._lock:
            if device_id is not None:
                rows = self._conn.execute(
                    "SELECT * FROM events WHERE nuki_id = ? ORDER BY id DESC",
                    (device_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM events ORDER BY id DESC"
                ).fetchall()

        for row in rows:
            entry = self._row_to_entry(row)
            local_ts = entry.timestamp.astimezone(zone)
            nuki_id = entry.payload.get("nukiId")
            # Prefer the name carried in the payload; otherwise resolve it from
            # the configured device names (real callbacks have no `name`) (#115).
            device_name = entry.payload.get("name") or names.get(nuki_id, "")

            writer.writerow([
                local_ts.strftime("%Y-%m-%d"),
                local_ts.strftime("%H:%M:%S"),
                entry.event_type or "Unknown",
                entry.payload.get("deviceType"),
                nuki_id,
                device_name,
                entry.payload.get("state"),
                entry.validation_result.valid,
                f"{entry.validation_result.delay_seconds:.2f}",
                entry.validation_result.reason or "",
                "; ".join(entry.actions),
                f"{entry.processing_time_ms:.2f}" if entry.processing_time_ms is not None else "",
                json.dumps(entry.payload, ensure_ascii=False),
            ])

        # BOM + Excel separator hint so Excel (incl. ES locale) parses columns.
        return "\ufeff" + "sep=,\r\n" + output.getvalue()

    def clear_log(self):
        """Clear all events from log (the DB file itself is kept)."""
        with self._lock:
            self._conn.execute("DELETE FROM events")
            self._conn.commit()

        logger.info("Event log cleared")

    def _cleanup_old_entries_locked(self):
        """Enforce retention + max-entries. Caller must hold ``self._lock``."""
        if self.retention_days:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=self.retention_days)
            ).isoformat()
            self._conn.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))

        if self.max_entries:
            self._conn.execute(
                "DELETE FROM events WHERE id NOT IN "
                "(SELECT id FROM events ORDER BY id DESC LIMIT ?)",
                (self.max_entries,),
            )

    def _cleanup_old_entries(self):
        """Public wrapper that locks and commits the retention/cap cleanup."""
        with self._lock:
            self._cleanup_old_entries_locked()
            self._conn.commit()
