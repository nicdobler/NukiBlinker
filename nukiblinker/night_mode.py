"""Night mode service.

Manages time-based notification behavior to reduce disruptions during
night hours by disabling audio and reducing light brightness.
"""

import logging
from datetime import datetime, time, timedelta
from typing import Optional

from .config import EventRuleConfig

logger = logging.getLogger(__name__)


class NightMode:
    """Manages time-based notification behavior."""

    def __init__(self, start_time: str = "22:00", end_time: str = "07:00",
                 brightness_factor: float = 0.3, grace_minutes: int = 5):
        """Initialize night mode with time range and settings.

        Args:
            start_time: Night mode start time in HH:MM format (24-hour)
            end_time: Night mode end time in HH:MM format (24-hour)
            brightness_factor: Factor to reduce brightness (0.0-1.0)
            grace_minutes: Grace period in minutes around boundaries
        """
        self.start_time_str = start_time
        self.end_time_str = end_time
        self.brightness_factor = max(0.0, min(1.0, brightness_factor))
        self.grace_minutes = grace_minutes

        try:
            self.start_time = self._parse_time(start_time)
            self.end_time = self._parse_time(end_time)
            logger.info(
                "NightMode initialized: %s to %s, brightness=%.1f%%, grace=%d min",
                start_time, end_time, self.brightness_factor * 100, grace_minutes
            )
        except ValueError as e:
            logger.error("Invalid time format for night mode: %s", e)
            # Default to disabled state
            self.start_time = None
            self.end_time = None

    def is_enabled(self) -> bool:
        """Check if night mode is properly configured."""
        return self.start_time is not None and self.end_time is not None

    def is_night_time(self) -> bool:
        """Check if current time is within night mode hours.

        Returns:
            True if current time is within night mode period (including grace period)
        """
        if not self.is_enabled():
            return False

        now = datetime.now()
        now_min = now.hour * 60 + now.minute

        # Work in minutes-of-day and wrap with modulo so the grace period is
        # correct even when it pushes a boundary across midnight (e.g. a
        # start of 00:02 with a 5-minute grace → effective start 23:57).
        start_min = self.start_time.hour * 60 + self.start_time.minute
        end_min = self.end_time.hour * 60 + self.end_time.minute
        effective_start = (start_min - self.grace_minutes) % 1440
        effective_end = (end_min + self.grace_minutes) % 1440

        if effective_start <= effective_end:
            # Window does not cross midnight.
            return effective_start <= now_min <= effective_end
        # Window crosses midnight (overnight range, or a grace-induced wrap).
        return now_min >= effective_start or now_min <= effective_end

    def apply_night_mode(self, rule: EventRuleConfig) -> EventRuleConfig:
        """Return modified rule for night mode.

        Args:
            rule: Original event rule configuration

        Returns:
            Modified rule for night mode, or original rule if not in night time
        """
        if not self.is_night_time():
            return rule

        # Create a deep copy of the rule
        night_rule = rule.model_copy(deep=True)

        # Disable audio notifications completely
        if night_rule.audio.enabled:
            night_rule.audio.enabled = False
            logger.debug("Night mode: disabled audio for event")

        # Built-in select/lselect blink brightness is controlled by the Hue
        # bridge and cannot be dimmed, so night mode only disables audio.
        # Note: HomeKit notifications remain enabled (silent push notifications)
        logger.debug("Night mode applied to event rule")

        return night_rule

    def get_next_change_time(self) -> Optional[datetime]:
        """Get the next time when night mode will change state.

        Returns:
            Next change time as datetime, or None if night mode is disabled
        """
        if not self.is_enabled():
            return None

        now = datetime.now()

        if self.is_night_time():
            # Currently in night mode, find end time
            if self.start_time <= self.end_time:
                # Same-day range
                next_change = datetime.combine(now.date(), self.end_time)
                if next_change <= now:
                    next_change += timedelta(days=1)
            else:
                # Overnight range
                next_change = datetime.combine(now.date(), self.end_time)
                if next_change <= now:
                    next_change += timedelta(days=1)
        else:
            # Currently in day mode, find start time
            if self.start_time <= self.end_time:
                # Same-day range
                next_change = datetime.combine(now.date(), self.start_time)
                if next_change <= now:
                    next_change += timedelta(days=1)
            else:
                # Overnight range
                next_change = datetime.combine(now.date(), self.start_time)
                if next_change <= now:
                    next_change += timedelta(days=1)

        return next_change

    def _parse_time(self, time_str: str) -> time:
        """Parse time string in HH:MM format.

        Args:
            time_str: Time string in HH:MM format

        Returns:
            time object

        Raises:
            ValueError: If time format is invalid
        """
        try:
            parts = time_str.split(':')
            if len(parts) != 2:
                raise ValueError("Time must be in HH:MM format")

            hour = int(parts[0])
            minute = int(parts[1])

            if not (0 <= hour <= 23) or not (0 <= minute <= 59):
                raise ValueError("Hour must be 0-23, minute must be 0-59")

            return time(hour, minute)

        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid time format '{time_str}': {e}")

    def update_settings(
        self, start_time: str = None, end_time: str = None,
        brightness_factor: float = None, grace_minutes: int = None
    ):
        """Update night mode settings.

        Args:
            start_time: New start time in HH:MM format
            end_time: New end time in HH:MM format
            brightness_factor: New brightness factor (0.0-1.0)
            grace_minutes: New grace period in minutes
        """
        if start_time is not None:
            self.start_time_str = start_time
            self.start_time = self._parse_time(start_time)

        if end_time is not None:
            self.end_time_str = end_time
            self.end_time = self._parse_time(end_time)

        if brightness_factor is not None:
            self.brightness_factor = max(0.0, min(1.0, brightness_factor))

        if grace_minutes is not None:
            self.grace_minutes = max(0, grace_minutes)

        logger.info(
                "NightMode settings updated: %s to %s, brightness=%.1f%%, grace=%d min",
                self.start_time_str, self.end_time_str,
                self.brightness_factor * 100, self.grace_minutes
            )

    def get_status(self) -> dict:
        """Get current night mode status.

        Returns:
            Dictionary with current status information
        """
        next_change = self.get_next_change_time()

        return {
            "enabled": self.is_enabled(),
            "active": self.is_night_time() if self.is_enabled() else False,
            "start_time": self.start_time_str,
            "end_time": self.end_time_str,
            "brightness_factor": self.brightness_factor,
            "grace_minutes": self.grace_minutes,
            "next_change": next_change.isoformat() if next_change else None,
            "current_time": datetime.now().isoformat()
        }
