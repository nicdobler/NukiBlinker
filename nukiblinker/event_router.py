"""Classifies Nuki callback events and dispatches to the matching rule."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from nukiblinker.logging_config import get_logger

if TYPE_CHECKING:
    from nukiblinker.config import AppConfig

logger = get_logger("event_router")

# Nuki Opener states (deviceType=2)
_OPENER_STATE_RING_TO_OPEN = 7  # opening (door being opened)
# Note: a doorbell ring is signalled by the callback's `ringactionState`/
# `ringactionTimestamp` fields (Bridge API §4), NOT by `state`. Opener
# `state == 1` is "online" (a routine status update) and must not be treated
# as a ring (#97).

# Nuki Smart Lock states (deviceType=0)
# Note: state 3 (unlocked) is deliberately NOT treated as door_opened —
# unlocking without opening must not trigger notifications (#60).
_LOCK_STATE_UNLATCHED = 5
_LOCK_STATE_UNLATCHING = 7  # actively unlatching = door being opened (#160)

# Door sensor states (doorsensorState field)
_DOORSENSOR_DOOR_OPENED = 3  # door physically opened (#169)

# Retry parameters for resolve_person() (#193/#197): the Nuki Web API can lag
# a few seconds behind the bridge callback, so we retry when the best candidate
# is older than _RESOLVE_RECENCY_S relative to the ringactionTimestamp.
_RESOLVE_MAX_RETRIES = 7      # max number of extra attempts (~14s total at 2s each)
_RESOLVE_RETRY_DELAY_S = 2    # seconds between retries
_RESOLVE_RECENCY_S = 10       # candidate must be within this many seconds of the ring

# Opener "online" status state (deviceType=2). Discovery probe target (#219).
_OPENER_STATE_ONLINE = 1

# Discovery probe parameters (#219/#220): an app-triggered open ("Abierta")
# surfaces on the Nuki Web log a few seconds *after* the bridge fires the
# Opener `state=1 online` callback, so the probe polls a handful of times.
_PROBE_MAX_ATTEMPTS = 5
_PROBE_DELAY_S = 3


def classify(payload: dict, config: AppConfig) -> str | None:
    """Return event type string or None if the payload should be ignored.

    Possible return values: 'ring', 'ring_to_open', 'door_opened'.

    Opener state machine (source of truth — official Nuki Bridge API):
      state=1  "online"     — RTO expired / post-open idle.    Ignore.
      state=3  "rto active" — Ring-to-Open mode activated.     Ignore.
      state=5  "open"       — Post-open settled state.         Ignore.
      state=7  "opening"    — Gate is opening NOW.             → ring_to_open
      ringactionState=true  — Someone pressed the doorbell.    → ring
    """
    device_type = payload.get("deviceType")
    nuki_id = payload.get("nukiId")
    state = payload.get("state")

    if device_type == 2:  # Opener
        if config.nuki.opener_id is not None and nuki_id != config.nuki.opener_id:
            logger.debug("Ignoring Opener %s (filter: %s)", nuki_id, config.nuki.opener_id)
            return None
        if state == _OPENER_STATE_RING_TO_OPEN:
            logger.info("Event classified: ring_to_open (Opener %s, state=%s)", nuki_id, state)
            return "ring_to_open"
        if payload.get("ringactionState") is True:
            logger.info(
                "Event classified: ring (Opener %s, ringactionTimestamp=%s)",
                nuki_id, payload.get("ringactionTimestamp"),
            )
            return "ring"
        # All other Opener states (online/rto-active/open/boot-run/etc.) are
        # routine status updates — ignore them (#197).
        logger.debug(
            "Opener status callback ignored: state=%s nukiId=%s ringactionState=%s",
            state, nuki_id, payload.get("ringactionState"),
        )
        return None

    if device_type == 0:  # Smart Lock
        if config.nuki.lock_id is not None and nuki_id != config.nuki.lock_id:
            logger.debug("Ignoring Smart Lock %s (filter: %s)", nuki_id, config.nuki.lock_id)
            return None
        door_sensor = payload.get("doorsensorState")
        is_door_opened = state in (_LOCK_STATE_UNLATCHED, _LOCK_STATE_UNLATCHING)
        is_door_opened |= door_sensor == _DOORSENSOR_DOOR_OPENED  # #169
        if is_door_opened:
            logger.info(
                "Event classified: door_opened (Lock %s, state=%s, doorsensorState=%s)",
                nuki_id, state, door_sensor,
            )
            return "door_opened"
        logger.debug("Ignoring Smart Lock state %s (nukiId=%s)", state, nuki_id)
        return None

    logger.debug("Ignoring unknown deviceType %s", device_type)
    return None


def _resolve_web_id(payload: dict, config) -> int | None:
    """Return the Nuki Web API ``smartlockId`` for the device in *payload*.

    The Nuki Bridge ``nukiId`` and the Nuki Web API ``smartlockId`` are
    different namespaces (#190).  When the user has configured the mapping via
    ``nuki.opener_web_id`` / ``nuki.lock_web_id``, that value is used; otherwise
    we return ``None`` so the caller queries the global (unscoped) log endpoint,
    which still works but is slightly less efficient for multi-device accounts.
    """
    if config is None:
        return None
    nuki_cfg = getattr(config, "nuki", None)
    if nuki_cfg is None:
        return None
    device_type = payload.get("deviceType")
    if device_type == 2:  # Opener
        return nuki_cfg.opener_web_id
    if device_type == 0:  # Smart Lock
        return nuki_cfg.lock_web_id
    return None


async def resolve_person(payload: dict, fallback_name: str = "Alguien",
                         *, nuki_web=None, config=None, sleep=None) -> dict:
    """Resolve the user name (and trigger) for the event via the Nuki Web API.

    Name resolution is done **exclusively** through the Nuki Web API (#175). The
    local Nuki Bridge ``/log`` endpoint never carries the caller's name for the
    cases we care about (it lags, and on the software bridge it has no name at
    all), so retrying against it only added latency and noise — it has been
    removed. When the Web API is not configured or cannot resolve a name, we
    return the configured ``fallback_name``.

    The Nuki Web API sometimes lags a few seconds behind the bridge callback
    (#193): the entry for the current ring may not yet be in the log on the
    first query. ``resolve_person`` retries up to ``_RESOLVE_MAX_RETRIES`` times
    (each ``_RESOLVE_RETRY_DELAY_S`` seconds apart) when the best candidate is
    older than ``_RESOLVE_RECENCY_S`` relative to ``ringactionTimestamp``. If the
    candidate is genuinely anonymous (no name in the most-recent non-sensor
    entry), no retry is done — anonymous opens are expected (#155).

    Returns context dict: {"name": "Nico", "name_source": ...} (plus "trigger"
    when known). ``name_source`` is one of "web_api" or "fallback" — the latter
    meaning no identity was resolved (e.g. an anonymous Ring-to-Open, or no Web
    API token), which is expected, not a failure (#155).
    """
    _sleep = sleep if sleep is not None else asyncio.sleep
    nuki_id = payload.get("nukiId")
    # Trigger code (how the action was performed). Captured for observability so
    # the user can confirm the real code before any suppression is wired (#97).
    resolved_trigger: int | None = None
    # Matched Web entry `date` (#204): exposed so the caller can log the *real*
    # event time (the open time) rather than the callback receive time. Only set
    # when the matched entry actually carries a date.
    resolved_event_time: str | None = None

    def _result(name: str, source: str) -> dict:
        out: dict = {"name": name, "name_source": source}
        if resolved_trigger is not None:
            out["trigger"] = resolved_trigger
        if resolved_event_time is not None:
            out["event_time"] = resolved_event_time
        return out

    if nuki_web is None:
        logger.info(
            "Nuki Web API not configured — cannot resolve name for nukiId=%s; using fallback",
            nuki_id,
        )
        return _result(fallback_name, "fallback")

    # Parse the ring timestamp from the payload so we can judge whether the
    # Web API entry we retrieved belongs to this event or is a stale older one.
    ring_ts = _parse_iso(payload.get("ringactionTimestamp"))

    try:
        from nukiblinker.nuki_web_client import TRIGGER_NAMES, SOURCE_DOOR_SENSOR

        web_id = _resolve_web_id(payload, config)

        for attempt in range(_RESOLVE_MAX_RETRIES + 1):
            entries = await nuki_web.get_recent_log(smartlock_id=web_id, limit=20)
            if not entries:
                logger.info("Nuki Web API log empty for nukiId=%s — using fallback", nuki_id)
                return _result(fallback_name, "fallback")

            # The most recent entry is the best candidate, but door-sensor entries
            # (source=SOURCE_DOOR_SENSOR) carry no name and arrive immediately after
            # an open, pushing the real named entry down the list (#157). Capture the
            # trigger from the most recent entry, then take the first non-sensor
            # entry. If that entry has no name, the open is genuinely anonymous and
            # we must NOT look further (only the most recent open counts — #155).
            most_recent = entries[0]
            resolved_trigger = most_recent.get("trigger")

            first_non_sensor = next(
                (e for e in entries if e.get("source") != SOURCE_DOOR_SENSOR),
                None,
            )
            candidate = first_non_sensor if first_non_sensor is not None else most_recent
            trigger_for_log = candidate.get("trigger")
            if trigger_for_log is not None:
                resolved_trigger = trigger_for_log

            # #193: check whether the candidate belongs to this ring. If ring_ts
            # is known and the candidate's date is older than _RESOLVE_RECENCY_S,
            # the Web API hasn't propagated the current event yet — retry.
            if ring_ts is not None and candidate.get("name"):
                candidate_ts = _parse_iso(candidate.get("date"))
                if candidate_ts is not None:
                    age = (ring_ts - candidate_ts).total_seconds()
                    if age > _RESOLVE_RECENCY_S:
                        if attempt < _RESOLVE_MAX_RETRIES:
                            logger.info(
                                "Web API candidate for nukiId=%s is stale (age=%.0fs > %ds) "
                                "— retry %d/%d in %ds",
                                nuki_id, age, _RESOLVE_RECENCY_S,
                                attempt + 1, _RESOLVE_MAX_RETRIES, _RESOLVE_RETRY_DELAY_S,
                            )
                            await _sleep(_RESOLVE_RETRY_DELAY_S)
                            continue
                        # Last attempt — still stale; fall back.
                        logger.info(
                            "Web API: candidate for nukiId=%s still stale after %d "
                            "retries — using fallback",
                            nuki_id, _RESOLVE_MAX_RETRIES,
                        )
                        return _result(fallback_name, "fallback")

            name = candidate.get("name")
            if name:
                # Surface the matched entry's date so the caller logs the real
                # event time (the open time), not the callback receive time (#204).
                resolved_event_time = candidate.get("date")
                logger.info(
                    "Resolved person via Web API: name=%s trigger=%s(%s) source=%s "
                    "date=%s (sensor_entries_skipped=%d, attempt=%d)",
                    name, resolved_trigger,
                    TRIGGER_NAMES.get(resolved_trigger, "unknown"),
                    candidate.get("source"),
                    resolved_event_time,
                    entries.index(candidate),
                    attempt,
                )
                return _result(name, "web_api")

            # Anonymous open: surface the trigger for observability (#97) but there
            # is no name to resolve — use the fallback. Do NOT retry: anonymous opens
            # are expected and the most-recent entry already tells the full story (#155).
            logger.info(
                "Web API: no name found for nukiId=%s (checked %d entries, "
                "first_non_sensor=%s); trigger=%s(%s) — using fallback",
                nuki_id,
                len(entries),
                first_non_sensor is not None,
                resolved_trigger,
                TRIGGER_NAMES.get(resolved_trigger, "unknown"),
            )
            return _result(fallback_name, "fallback")

    except Exception:
        logger.warning(
            "Nuki Web API resolution failed for nukiId=%s — using fallback",
            nuki_id, exc_info=True,
        )
        return _result(fallback_name, "fallback")


def is_opener_status_probe_candidate(payload: dict, config) -> bool:
    """True for an Opener ``state=1 online`` status callback (not a ring).

    This is the bridge signal that *accompanies* an app-triggered open
    ("Abierta") — see #219. It is deliberately distinct from a ring
    (``ringactionState=true``) and from ``state=7`` (RTO / opener button).
    Honours the ``nuki.opener_id`` filter when configured.
    """
    if payload.get("deviceType") != 2:
        return False
    if payload.get("state") != _OPENER_STATE_ONLINE:
        return False
    if payload.get("ringactionState") is True:
        return False
    opener_id = getattr(getattr(config, "nuki", None), "opener_id", None)
    if opener_id is not None and payload.get("nukiId") != opener_id:
        return False
    return True


async def discovery_probe_app_open(payload: dict, config, clients, *, sleep=None) -> None:
    """LOG-ONLY discovery probe for #219/#220 — never dispatches or notifies.

    On an Opener ``state=1 online`` callback, poll the Nuki Web log a few times
    and log the most-recent entry's distinguishing fields (``action`` /
    ``openerLog.activeRto`` / ``name`` / ``trigger`` / ``source``). An
    app-triggered open ("Abierta") surfaces a few seconds after the callback, so
    polling captures it. The purpose is to confirm the real codes that separate
    an app open from a Ring-to-Open / opener-button open before wiring the
    actual classification (#219/#220). This function changes no behaviour.
    """
    _sleep = sleep if sleep is not None else asyncio.sleep
    nuki_web = getattr(clients, "nuki_web", None)
    if nuki_web is None:
        return
    nuki_id = payload.get("nukiId")
    web_id = _resolve_web_id(payload, config)
    for attempt in range(_PROBE_MAX_ATTEMPTS):
        try:
            entries = await nuki_web.get_recent_log(smartlock_id=web_id, limit=20)
        except Exception:
            logger.warning("[#219 discovery] Nuki Web query failed", exc_info=True)
            return
        top = entries[0] if entries else None
        if top is not None:
            opener_log = top.get("openerLog") or {}
            logger.info(
                "[#219 discovery] Opener %s online — Nuki Web top entry "
                "(attempt %d/%d): name=%r action=%s state=%s trigger=%s source=%s "
                "activeRto=%s date=%s",
                nuki_id, attempt + 1, _PROBE_MAX_ATTEMPTS,
                top.get("name"), top.get("action"), top.get("state"),
                top.get("trigger"), top.get("source"),
                opener_log.get("activeRto"), top.get("date"),
            )
        else:
            logger.info(
                "[#219 discovery] Opener %s online — Nuki Web log empty (attempt %d/%d)",
                nuki_id, attempt + 1, _PROBE_MAX_ATTEMPTS,
            )
        if attempt < _PROBE_MAX_ATTEMPTS - 1:
            await _sleep(_PROBE_DELAY_S)


async def dispatch(
    event_type: str, payload: dict, config: AppConfig, clients,
    *, context_override: dict | None = None,
) -> None:
    """Look up the event rule and fire matching notification channels."""
    from nukiblinker import notifier  # noqa: E402 — deferred to avoid circular import

    rule = getattr(config.events, event_type, None)
    if rule is None:
        logger.warning("No event rule for type '%s'", event_type)
        return

    if context_override is not None:
        context = context_override
    elif event_type in ("ring", "ring_to_open"):
        # Opener events resolve the caller's name via the Nuki Web API only
        # (#175/#177). door_opened deliberately does NOT resolve a name — its
        # only actions are chime/blink, the opener identity is irrelevant (#176).
        fallback = rule.audio.fallback_name if rule.audio else "Alguien"
        context = await resolve_person(
            payload, fallback, nuki_web=getattr(clients, "nuki_web", None),
            config=config,
        )
    else:
        context = {}

    logger.info("Dispatching event '%s' with context %s", event_type, context)
    await notifier.notify(rule, config, clients, context)


async def dispatch_with_actions(
    event_type: str, payload: dict, config: AppConfig, clients, rule,
    *, context_override: dict | None = None,
) -> list[str]:
    """Look up the event rule and fire matching notification channels, returning actions taken.

    Returns:
        List of action descriptions (e.g., ["Hue lights blinked", "TTS played"])
    """
    from nukiblinker import notifier  # noqa: E402 — deferred to avoid circular import

    if rule is None:
        logger.warning("No event rule for type '%s'", event_type)
        return []

    if context_override is not None:
        context = context_override
    elif event_type in ("ring", "ring_to_open"):
        # Opener events resolve the caller's name via the Nuki Web API only
        # (#175/#177). door_opened deliberately does NOT resolve a name — its
        # only actions are chime/blink, the opener identity is irrelevant (#176).
        fallback = rule.audio.fallback_name if rule.audio else "Alguien"
        context = await resolve_person(
            payload, fallback, nuki_web=getattr(clients, "nuki_web", None),
            config=config,
        )
    else:
        context = {}

    logger.info("Dispatching event '%s' with context %s", event_type, context)
    actions = await notifier.notify_with_actions(rule, config, clients, context)

    # Surface an anonymous open in the Event Log so a name-less Ring-to-Open is
    # not mistaken for a failure — it has no associated identity by design (#155).
    if context.get("name_source") == "fallback":
        actions.insert(0, "Name: anonymous (no identity resolved)")

    # Surface the resolved trigger in the Event Log so the user can confirm the
    # real trigger code (e.g. physical button) before any suppression is wired (#97).
    trigger = context.get("trigger")
    if trigger is not None:
        from nukiblinker.nuki_web_client import TRIGGER_NAMES
        actions.insert(0, f"Trigger: {TRIGGER_NAMES.get(trigger, 'unknown')} ({trigger})")

    return actions


def _parse_iso(value) -> datetime | None:
    """Parse an ISO-8601 string into a tz-aware UTC datetime, or None."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def event_time_for_log(payload: dict, context: dict | None = None) -> datetime:
    """Return the *real* event time (UTC) to record in the Event Log (#204).

    The Bridge callback's receive time is NOT the event time: a buffered or
    delayed callback would otherwise log "strange hours" (#204). Precedence:

    1. A **fresh ring** (``ringactionState`` true) carries the real ring time in
       ``ringactionTimestamp`` — use it.
    2. For a ``ring_to_open`` the Bridge gives no fresh timestamp
       (``ringactionTimestamp`` is the *last* ring and is frequently stale), so
       use the matched Nuki Web entry ``date`` surfaced by ``resolve_person`` in
       ``context["event_time"]``.
    3. Otherwise (``door_opened``, anonymous opens, no Web match) fall back to
       the callback receive time, ``datetime.now(UTC)``.

    All returned values are timezone-aware UTC; the UI/CSV convert to local.
    """
    if payload.get("ringactionState") is True:
        dt = _parse_iso(payload.get("ringactionTimestamp"))
        if dt is not None:
            return dt
    if context:
        dt = _parse_iso(context.get("event_time"))
        if dt is not None:
            return dt
    return datetime.now(timezone.utc)


# A genuine fresh ring should carry a ringactionTimestamp only a few seconds
# old: the Bridge resets ringactionState after ~30 s, so a fresh-ring callback
# always arrives right after the ring. A much older timestamp on a fresh ring
# is the only legitimate "strange hours" signal — it hints the callback was
# buffered/delayed or the Bridge clock has drifted. (A stale timestamp on a
# NON-fresh callback, ringactionState false, is normal: it is just the *last*
# ring and is expected to be old, so it must NOT warn.)
RINGACTION_STALE_THRESHOLD_S = 120


def ringaction_staleness(payload: dict, *, now: datetime | None = None) -> float | None:
    """Age in seconds of ``ringactionTimestamp`` for a **fresh ring**.

    Returns the positive age (now - ringactionTimestamp) only when
    ``ringactionState`` is true and ``ringactionTimestamp`` parses; otherwise
    ``None`` (not a fresh ring, or no/invalid timestamp — nothing to warn about).

    Callers compare the result against :data:`RINGACTION_STALE_THRESHOLD_S` to
    decide whether to emit a staleness WARNING. A future-dated timestamp yields
    a negative value (never stale).
    """
    if payload.get("ringactionState") is not True:
        return None
    dt = _parse_iso(payload.get("ringactionTimestamp"))
    if dt is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - dt).total_seconds()
