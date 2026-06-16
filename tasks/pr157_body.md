## Summary

Fixes #157 — incorrect event mapping, missing identity resolution, and silent RTO duplicate notifications.

### Changes

**Paso 4 — `resolve_person` Web API sensor skip (highest impact)**
- Door-sensor log entries (`source=2`) now skipped when looking for the opener's identity. Previously `entries[0]` could be a nameless sensor entry, pushing the real named entry (Nico, Ele, etc.) out of sight.
- Stops at the first non-sensor entry: if that entry has no name, the open is genuinely anonymous (preserves #155 anti-stale fix).
- Added `SOURCE_DOOR_SENSOR = 2` constant to `nuki_web_client.py`.

**Paso 2 — Deduplication RTO fallback when `ringactionTimestamp` absent**
- Some bridge firmware omits `ringactionTimestamp` in the `ring_to_open` (state=7) callback, breaking the existing cross-event dedup key.
- Added `_rto_fallback_key` using `(nukiId, "rto_seen")`: registered only when a `ring_to_open` is accepted, suppresses a subsequent `ring` from the same device within the window.
- Standalone rings (no prior `ring_to_open`) are never suppressed by the fallback key.

**Paso 3 — Opener diagnostics**
- Ignored Opener callbacks now log at INFO with full payload (state, ringactionState, ringactionTimestamp) instead of DEBUG, making it possible to identify exactly what arrives when Irlene opens from the app.

### Tests
- `test_deduplication.py`: updated `test_ring_to_open_without_timestamp_*` + 4 new tests for fbkey behaviour.
- `test_event_router.py`: 2 new tests for sensor-skip logic in `resolve_person`.
