"""Event timestamp validation service.

Validates that Nuki events are processed within an acceptable time threshold
to prevent notifications for stale events.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of event validation."""
    valid: bool
    delay_seconds: float
    reason: Optional[str] = None


class EventValidator:
    """Validates event timestamps before processing."""

    def __init__(self, max_delay_seconds: int = 60):
        """Initialize validator with maximum allowed delay.

        Args:
            max_delay_seconds: Maximum allowed delay in seconds before rejecting events
        """
        self.max_delay_seconds = max_delay_seconds
        logger.info("EventValidator initialized with max_delay_seconds=%d", max_delay_seconds)

    def validate_event(self, payload: dict) -> ValidationResult:
        """Check if event timestamp is within acceptable delay.

        Args:
            payload: Nuki callback payload

        Returns:
            ValidationResult with validation status and details
        """
        try:
            event_time = self._extract_timestamp(payload)
            if event_time is None:
                # If no timestamp, assume event is valid (fallback behavior)
                logger.debug("No timestamp found in payload, assuming event is valid")
                return ValidationResult(valid=True, delay_seconds=0.0)

            now = datetime.now(timezone.utc)
            delay = (now - event_time).total_seconds()

            if delay < 0:
                # Event timestamp is in the future - could be clock sync issue
                logger.warning(
                    "Event timestamp is in the future: %s, delay: %.2f seconds",
                    event_time.isoformat(), delay
                )
                # Allow future events within a small window (5 minutes) for clock sync
                if abs(delay) > 300:  # 5 minutes
                    return ValidationResult(
                        valid=False,
                        delay_seconds=delay,
                        reason=f"Event timestamp is too far in the future: {abs(delay):.1f}s"
                    )
                return ValidationResult(valid=True, delay_seconds=delay)

            is_valid = delay <= self.max_delay_seconds
            reason = None
            if not is_valid:
                reason = f"Event too old: {delay:.1f}s (max: {self.max_delay_seconds}s)"
                logger.warning("Event rejected: %s", reason)
            else:
                logger.debug("Event validated: delay=%.2f seconds", delay)

            return ValidationResult(
                valid=is_valid,
                delay_seconds=delay,
                reason=reason
            )

        except Exception as e:
            logger.error("Error validating event: %s", e)
            # On validation error, allow event to proceed (fail-safe)
            return ValidationResult(
                valid=True,
                delay_seconds=0.0,
                reason=f"Validation error: {e}"
            )

    def _extract_timestamp(self, payload: dict) -> Optional[datetime]:
        """Extract the event timestamp from a Nuki callback payload.

        Field precedence (#115): for an active ring, the Bridge's top-level
        ``timestamp`` is the *"retrieval of this lock state"* (per Bridge API
        §4) and is frequently stale, which made genuine rings be rejected as
        "too old". The actual ring time is ``ringactionTimestamp``, so it is
        preferred whenever a ring action is currently occurring
        (``ringactionState`` truthy). Otherwise we fall back to ``timestamp``
        and a few alternative field names. If nothing is found we cannot
        validate the event and treat it as valid (handled by the caller).

        Args:
            payload: Nuki callback payload

        Returns:
            Event timestamp in UTC or None if not found
        """
        # An active ring action carries the real ring time in
        # ringactionTimestamp; prefer it over the stale lock-state timestamp.
        if payload.get("ringactionState") and payload.get("ringactionTimestamp") is not None:
            try:
                return self._parse_timestamp_value(payload["ringactionTimestamp"])
            except (ValueError, OSError) as e:
                logger.debug("Failed to parse ringactionTimestamp %s: %s",
                             payload.get("ringactionTimestamp"), e)

        # Fall back to the generic timestamp fields, in order of preference.
        for field in ("timestamp", "time", "created_at", "eventTime"):
            value = payload.get(field)
            if value is None:
                continue
            try:
                return self._parse_timestamp_value(value)
            except (ValueError, OSError) as e:
                logger.debug("Failed to parse %s %s: %s", field, value, e)
                continue

        logger.debug("No timestamp found in payload")
        return None

    def _parse_timestamp_value(self, timestamp) -> datetime:
        """Parse a timestamp value into a datetime object.

        Args:
            timestamp: The timestamp value to parse

        Returns:
            datetime object in UTC

        Raises:
            ValueError: If timestamp cannot be parsed
        """
        # Handle both Unix timestamp (seconds) and milliseconds
        if isinstance(timestamp, (int, float)):
            # Determine if it's seconds or milliseconds based on magnitude
            if timestamp > 1e10:  # Milliseconds (since year 2286)
                timestamp_seconds = timestamp / 1000
            else:  # Seconds
                timestamp_seconds = timestamp

            return datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc)
        elif isinstance(timestamp, str):
            # Try ISO format first
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                # Normalize naive datetimes (no tz info) to UTC so they can be
                # compared against the timezone-aware ``now`` in validate_event;
                # otherwise the subtraction raises TypeError and is swallowed by
                # the fail-safe, silently accepting stale events (#143).
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                # Try Unix timestamp as string
                timestamp_float = float(timestamp)
                if timestamp_float > 1e10:
                    timestamp_seconds = timestamp_float / 1000
                else:
                    timestamp_seconds = timestamp_float
                return datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc)
        else:
            raise ValueError(f"Unsupported timestamp type: {type(timestamp)}")
