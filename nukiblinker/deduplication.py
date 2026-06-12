"""Event deduplication.

A single real interaction makes the Nuki Bridge emit several callbacks (status
transitions plus the ring/open). Without deduplication each one fires the
notification channels, so a single ring/open can blast the speakers multiple
times (#97).

The deduplicator keeps an in-memory cache of recently *accepted* events and
suppresses equivalent ones within a configurable window. The dedup key is
``(nukiId, event_type, discriminator)`` where the discriminator is:

- the ``ringactionTimestamp`` for ``ring`` events, so a genuine second ring
  (which carries a new timestamp) is NOT treated as a duplicate, while repeated
  callbacks for the *same* ring are collapsed;
- the lock ``state`` for every other event type.
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Any, Dict, Optional, Tuple

from nukiblinker.logging_config import get_logger

logger = get_logger("deduplication")


class Deduplicator:
    """Suppresses duplicate events within a sliding time window."""

    def __init__(self, window_seconds: int = 120, enabled: bool = True,
                 time_func=time.monotonic) -> None:
        """Initialize the deduplicator.

        Args:
            window_seconds: Suppress equivalent events seen within this window.
            enabled: When False, ``is_duplicate`` always returns False.
            time_func: Monotonic clock source (injectable for tests).
        """
        self.window_seconds = window_seconds
        self.enabled = enabled
        self._time = time_func
        self._recent: Dict[Tuple[Any, ...], float] = {}
        self._lock = Lock()

    @staticmethod
    def _key(payload: dict, event_type: str) -> Tuple[Any, ...]:
        """Build the dedup key for an event."""
        if event_type == "ring":
            discriminator = payload.get("ringactionTimestamp")
        else:
            discriminator = payload.get("state")
        return (payload.get("nukiId"), event_type, discriminator)

    def is_duplicate(self, payload: dict, event_type: str) -> bool:
        """Return True if an equivalent event was accepted within the window.

        Records the event as accepted (resetting its window) when it is NOT a
        duplicate. Expired keys are pruned on every call.

        Args:
            payload: Nuki callback payload.
            event_type: Classified event type (e.g. "ring", "ring_to_open").
        """
        if not self.enabled:
            return False

        now = self._time()
        key = self._key(payload, event_type)

        with self._lock:
            self._prune(now)
            last = self._recent.get(key)
            if last is not None and (now - last) <= self.window_seconds:
                logger.info(
                    "Duplicate event suppressed: %s (within %.0fs)",
                    key, now - last,
                )
                return True
            self._recent[key] = now
            return False

    def _prune(self, now: float) -> None:
        """Drop keys older than the window (caller holds the lock)."""
        expired = [
            k for k, ts in self._recent.items()
            if (now - ts) > self.window_seconds
        ]
        for k in expired:
            del self._recent[k]
