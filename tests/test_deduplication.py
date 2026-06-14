"""Tests for nukiblinker.deduplication — burst suppression with double-ring passthrough (#97)."""

from nukiblinker.deduplication import Deduplicator


class _Clock:
    """Controllable monotonic clock for deterministic tests."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def _ring(ts):
    return {"deviceType": 2, "nukiId": 1, "state": 1,
            "ringactionState": True, "ringactionTimestamp": ts}


class TestDeduplicator:
    def test_first_event_not_duplicate(self):
        dedup = Deduplicator(window_seconds=120, time_func=_Clock())
        assert dedup.is_duplicate(_ring("T1"), "ring") is False

    def test_repeat_same_ring_within_window_is_duplicate(self):
        clock = _Clock()
        dedup = Deduplicator(window_seconds=120, time_func=clock)
        assert dedup.is_duplicate(_ring("T1"), "ring") is False
        clock.advance(5)
        # same ringactionTimestamp → same ring → suppressed
        assert dedup.is_duplicate(_ring("T1"), "ring") is True

    def test_second_distinct_ring_passes(self):
        """A genuine second ring carries a new ringactionTimestamp → not a duplicate."""
        clock = _Clock()
        dedup = Deduplicator(window_seconds=120, time_func=clock)
        assert dedup.is_duplicate(_ring("T1"), "ring") is False
        clock.advance(10)
        assert dedup.is_duplicate(_ring("T2"), "ring") is False

    def test_duplicate_expires_after_window(self):
        clock = _Clock()
        dedup = Deduplicator(window_seconds=120, time_func=clock)
        assert dedup.is_duplicate(_ring("T1"), "ring") is False
        clock.advance(121)
        assert dedup.is_duplicate(_ring("T1"), "ring") is False

    def test_open_burst_deduped_by_state(self):
        clock = _Clock()
        dedup = Deduplicator(window_seconds=120, time_func=clock)
        payload = {"deviceType": 2, "nukiId": 1, "state": 7}
        assert dedup.is_duplicate(payload, "ring_to_open") is False
        clock.advance(2)
        assert dedup.is_duplicate(payload, "ring_to_open") is True

    def test_different_event_types_not_duplicate(self):
        dedup = Deduplicator(window_seconds=120, time_func=_Clock())
        assert dedup.is_duplicate(_ring("T1"), "ring") is False
        assert dedup.is_duplicate({"nukiId": 1, "state": 7}, "ring_to_open") is False

    def test_different_devices_not_duplicate(self):
        dedup = Deduplicator(window_seconds=120, time_func=_Clock())
        a = {"deviceType": 0, "nukiId": 1, "state": 5}
        b = {"deviceType": 0, "nukiId": 2, "state": 5}
        assert dedup.is_duplicate(a, "door_opened") is False
        assert dedup.is_duplicate(b, "door_opened") is False

    def test_disabled_never_duplicate(self):
        clock = _Clock()
        dedup = Deduplicator(window_seconds=120, enabled=False, time_func=clock)
        assert dedup.is_duplicate(_ring("T1"), "ring") is False
        assert dedup.is_duplicate(_ring("T1"), "ring") is False

    def test_open_distinct_timestamps_pass(self):
        """Two genuinely distinct door opens (different timestamps) are not collapsed.

        Regression: previously the discriminator for non-ring events was the
        constant ``state``, so a second real open within the window was wrongly
        suppressed.
        """
        clock = _Clock()
        dedup = Deduplicator(window_seconds=120, time_func=clock)
        a = {"nukiId": 1, "state": 5, "timestamp": "2026-06-13T10:00:00Z"}
        b = {"nukiId": 1, "state": 5, "timestamp": "2026-06-13T10:00:30Z"}
        assert dedup.is_duplicate(a, "door_opened") is False
        clock.advance(30)
        assert dedup.is_duplicate(b, "door_opened") is False

    def test_open_same_timestamp_is_duplicate(self):
        """Repeated callbacks for the same open (same timestamp) are suppressed."""
        clock = _Clock()
        dedup = Deduplicator(window_seconds=120, time_func=clock)
        p = {"nukiId": 1, "state": 5, "timestamp": "2026-06-13T10:00:00Z"}
        assert dedup.is_duplicate(p, "door_opened") is False
        clock.advance(5)
        assert dedup.is_duplicate(p, "door_opened") is True


def _rto_open(ts):
    """state 7 ring_to_open callback carrying the ring time (Bridge API §4)."""
    return {"deviceType": 2, "nukiId": 1, "state": 7,
            "ringactionState": False, "ringactionTimestamp": ts}


def _rto_ring(ts):
    """The follow-up state 1 callback with ringactionState true for the same RTO."""
    return {"deviceType": 2, "nukiId": 1, "state": 1,
            "ringactionState": True, "ringactionTimestamp": ts}


class TestRingToOpenCorrelation:
    """#121: one RTO emits ring_to_open + ring sharing ringactionTimestamp."""

    def test_ring_after_ring_to_open_suppressed(self):
        """ring_to_open fires; the paired ring (same ts) is suppressed."""
        clock = _Clock()
        dedup = Deduplicator(window_seconds=120, time_func=clock)
        assert dedup.is_duplicate(_rto_open("T1"), "ring_to_open") is False
        clock.advance(10)
        assert dedup.is_duplicate(_rto_ring("T1"), "ring") is True

    def test_ring_to_open_after_ring_suppressed(self):
        """Symmetric: ring first, then ring_to_open (same ts) is suppressed."""
        clock = _Clock()
        dedup = Deduplicator(window_seconds=120, time_func=clock)
        assert dedup.is_duplicate(_rto_ring("T1"), "ring") is False
        clock.advance(10)
        assert dedup.is_duplicate(_rto_open("T1"), "ring_to_open") is True

    def test_distinct_rto_interactions_not_suppressed(self):
        """Two RTOs with different ring timestamps each notify once."""
        clock = _Clock()
        dedup = Deduplicator(window_seconds=120, time_func=clock)
        assert dedup.is_duplicate(_rto_open("T1"), "ring_to_open") is False
        clock.advance(10)
        assert dedup.is_duplicate(_rto_ring("T1"), "ring") is True
        clock.advance(10)
        # A genuinely new RTO (new ringactionTimestamp) must pass.
        assert dedup.is_duplicate(_rto_open("T2"), "ring_to_open") is False

    def test_correlation_expires_after_window(self):
        """A ring far after the ring_to_open is no longer correlated."""
        clock = _Clock()
        dedup = Deduplicator(window_seconds=120, time_func=clock)
        assert dedup.is_duplicate(_rto_open("T1"), "ring_to_open") is False
        clock.advance(121)
        assert dedup.is_duplicate(_rto_ring("T1"), "ring") is False

    def test_ring_to_open_without_timestamp_not_correlated(self):
        """No ringactionTimestamp → nothing to correlate, ring still notifies."""
        clock = _Clock()
        dedup = Deduplicator(window_seconds=120, time_func=clock)
        bare = {"deviceType": 2, "nukiId": 1, "state": 7}
        assert dedup.is_duplicate(bare, "ring_to_open") is False
        clock.advance(10)
        assert dedup.is_duplicate(_rto_ring("T1"), "ring") is False
