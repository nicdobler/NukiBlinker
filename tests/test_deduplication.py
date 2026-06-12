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
