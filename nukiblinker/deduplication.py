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

Ring-to-Open correlation (#121)
-------------------------------
A single Ring-to-Open interaction makes the Opener emit two callbacks that
classify as *different* event types ~10s apart: a ``ring_to_open`` (state 7)
and a ``ring`` (``ringactionState`` true). Because their ``event_type`` differs
the per-type key above does not collapse them, so the user gets two
notifications for one RTO. Every Opener callback carries the same
``ringactionTimestamp`` (the time of the ring that triggered the open, Bridge
API §4), so we additionally suppress a second RTO-family event sharing the
key ``(nukiId, ringactionTimestamp)`` within the window — regardless of
event_type. Two genuinely distinct rings carry different timestamps and are
never collapsed.
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Any, Dict, Tuple

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
        # Cross-event RTO correlation: (nukiId, ringactionTimestamp) -> ts (#121)
        self._interactions: Dict[Tuple[Any, ...], float] = {}
        self._lock = Lock()

    @staticmethod
    def _key(payload: dict, event_type: str) -> Tuple[Any, ...]:
        """Build the dedup key for an event."""
        if event_type == "ring":
            discriminator = payload.get("ringactionTimestamp")
        else:
            # Prefer a per-event timestamp so two genuinely distinct events of
            # the same type (whose ``state`` is constant, e.g. door_opened=5,
            # ring_to_open=7) are not collapsed. Fall back to ``state`` when the
            # bridge payload carries no timestamp (preserving burst suppression).
            discriminator = (
                payload.get("timestamp")
                or payload.get("ringactionTimestamp")
                or payload.get("state")
            )
        return (payload.get("nukiId"), event_type, discriminator)

    # Event types produced by a single Ring-to-Open interaction (#121).
    _RTO_FAMILY = frozenset({"ring", "ring_to_open"})

    @classmethod
    def _interaction_key(cls, payload: dict, event_type: str) -> Tuple[Any, ...] | None:
        """Build the cross-event RTO key, or None when not applicable.

        A Ring-to-Open emits a ``ring_to_open`` and a ``ring`` that share the
        same ``ringactionTimestamp``. Correlating on ``(nukiId,
        ringactionTimestamp)`` lets us collapse the pair into one notification
        (#121). Returns None for non-RTO events or when the payload carries no
        ``ringactionTimestamp`` (nothing to correlate on).
        """
        if event_type not in cls._RTO_FAMILY:
            return None
        rats = payload.get("ringactionTimestamp")
        if rats is None:
            return None
        return (payload.get("nukiId"), rats)

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

            # Ring-to-Open correlation (#121): a ring + ring_to_open from the
            # same RTO share (nukiId, ringactionTimestamp). Suppress the second
            # one even though its event_type differs.
            ikey = self._interaction_key(payload, event_type)
            if ikey is not None:
                iseen = self._interactions.get(ikey)
                if iseen is not None and (now - iseen) <= self.window_seconds:
                    logger.info(
                        "Ring-to-Open duplicate suppressed: %s as '%s' "
                        "(within %.0fs of the first RTO callback)",
                        ikey, event_type, now - iseen,
                    )
                    self._interactions[ikey] = now
                    return True
                self._interactions[ikey] = now

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
        expired_i = [
            k for k, ts in self._interactions.items()
            if (now - ts) > self.window_seconds
        ]
        for k in expired_i:
            del self._interactions[k]
