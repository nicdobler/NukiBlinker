"""Classifies Nuki callback events and dispatches to the matching rule."""

from __future__ import annotations

import asyncio
import time as _time
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

# Opener status callbacks that classify() now surfaces for Nuki Web correlation
# (#180) instead of silently ignoring them.
OPENER_STATUS = "opener_status"

# Per-device cooldown guard for opener correlation (#180): prevents overlapping
# poll runs and re-firing from the burst of status callbacks one open emits.
_correlation_block_until: dict = {}


def classify(payload: dict, config: AppConfig) -> str | None:
    """Return event type string or None if the payload should be ignored.

    Possible return values: 'ring', 'ring_to_open', 'door_opened',
    'opener_status'. ``opener_status`` is returned for Opener callbacks that
    match the configured opener but are neither a ring nor a ring_to_open
    (e.g. routine ``state=1`` online / ``state=3`` rto-active updates). These
    used to be ignored; they are now surfaced so the dispatcher can correlate
    them with the Nuki Web activity log to detect a user-driven open (#180).
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
        # Not a ring/ring_to_open, but it IS our Opener. Surface it as a status
        # callback so the dispatcher can correlate it with Nuki Web to catch a
        # user-driven open that the bridge never reported as state=7 (#180).
        logger.info(
            "Opener status callback (will correlate with Nuki Web): state=%s "
            "nukiId=%s ringactionState=%s ringactionTimestamp=%s — full payload: %s",
            state, nuki_id, payload.get("ringactionState"),
            payload.get("ringactionTimestamp"), payload,
        )
        return OPENER_STATUS

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
                         *, nuki_web=None, config=None) -> dict:
    """Resolve the user name (and trigger) for the event via the Nuki Web API.

    Name resolution is done **exclusively** through the Nuki Web API (#175). The
    local Nuki Bridge ``/log`` endpoint never carries the caller's name for the
    cases we care about (it lags, and on the software bridge it has no name at
    all), so retrying against it only added latency and noise — it has been
    removed. When the Web API is not configured or cannot resolve a name, we
    return the configured ``fallback_name``.

    Returns context dict: {"name": "Nico", "name_source": ...} (plus "trigger"
    when known). ``name_source`` is one of "web_api" or "fallback" — the latter
    meaning no identity was resolved (e.g. an anonymous Ring-to-Open, or no Web
    API token), which is expected, not a failure (#155).
    """
    nuki_id = payload.get("nukiId")
    # Trigger code (how the action was performed). Captured for observability so
    # the user can confirm the real code before any suppression is wired (#97).
    resolved_trigger: int | None = None

    def _result(name: str, source: str) -> dict:
        out: dict = {"name": name, "name_source": source}
        if resolved_trigger is not None:
            out["trigger"] = resolved_trigger
        return out

    if nuki_web is None:
        logger.info(
            "Nuki Web API not configured — cannot resolve name for nukiId=%s; using fallback",
            nuki_id,
        )
        return _result(fallback_name, "fallback")

    try:
        from nukiblinker.nuki_web_client import TRIGGER_NAMES, SOURCE_DOOR_SENSOR

        web_id = _resolve_web_id(payload, config)
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
        name = candidate.get("name")
        trigger_for_log = candidate.get("trigger")
        if trigger_for_log is not None:
            resolved_trigger = trigger_for_log

        if name:
            logger.info(
                "Resolved person via Web API: name=%s trigger=%s(%s) source=%s "
                "(sensor_entries_skipped=%d)",
                name, resolved_trigger,
                TRIGGER_NAMES.get(resolved_trigger, "unknown"),
                candidate.get("source"),
                entries.index(candidate),
            )
            return _result(name, "web_api")

        # Anonymous open: surface the trigger for observability (#97) but there
        # is no name to resolve — use the fallback.
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


def _find_recent_user_open(entries: list[dict], *, now: datetime,
                           recency_seconds: int) -> dict | None:
    """Return the most recent user-attributed open entry, if it is recent.

    Reuses the same "most recent non-sensor entry wins" rule as
    ``resolve_person`` (#155/#157): door-sensor entries carry no identity and
    are skipped, but the first non-sensor entry is decisive — if it has no name
    the open is anonymous and we do not look further. The entry is only accepted
    when its ``date`` is within ``recency_seconds`` of ``now`` so an old open is
    not mistaken for the one that just happened. When the entry has no parseable
    ``date`` we accept it (best-effort), since polling already scoped it in time.
    """
    from nukiblinker.nuki_web_client import SOURCE_DOOR_SENSOR

    first_non_sensor = next(
        (e for e in entries if e.get("source") != SOURCE_DOOR_SENSOR),
        None,
    )
    if first_non_sensor is None or not first_non_sensor.get("name"):
        return None
    date = _parse_iso(first_non_sensor.get("date"))
    if date is not None and abs((now - date).total_seconds()) > recency_seconds:
        return None
    return first_non_sensor


async def correlate_opener_open(
    payload: dict, config: AppConfig, clients,
    *, sleep=None, time_func=None, now_func=None,
) -> dict | None:
    """Poll the Nuki Web log to detect a user-driven Opener open (#180).

    Some user opens (e.g. opening from the app while RTO is active) never produce
    a ``ring_to_open`` (state 7) callback — only routine ``opener_status``
    callbacks arrive. This polls the Nuki Web activity log for a short window
    after such a callback; if a user-attributed open appears it returns a context
    dict (``{"name", "name_source": "web_api", "trigger"?}``) for the caller to
    dispatch as a ``ring_to_open``. Returns ``None`` when nothing correlates.

    A per-device cooldown guard collapses the burst of status callbacks one open
    emits into a single poll run and prevents re-firing within the window.
    """
    sleep = sleep or asyncio.sleep
    time_func = time_func or _time.monotonic
    now_func = now_func or (lambda: datetime.now(timezone.utc))

    nuki_id = payload.get("nukiId")
    cfg = config.opener_correlation
    if not cfg.enabled:
        logger.debug("Opener correlation disabled — ignoring status callback for nukiId=%s", nuki_id)
        return None

    nuki_web = getattr(clients, "nuki_web", None)
    if nuki_web is None:
        logger.info(
            "Opener status callback for nukiId=%s ignored — Nuki Web not configured, "
            "cannot correlate", nuki_id,
        )
        return None

    mono = time_func()
    if mono < _correlation_block_until.get(nuki_id, 0.0):
        logger.debug(
            "Opener correlation already running/cooling down for nukiId=%s — skipping",
            nuki_id,
        )
        return None
    # Block overlapping poll runs for the duration of the window.
    _correlation_block_until[nuki_id] = mono + cfg.window_seconds

    logger.info(
        "Correlating opener status callback for nukiId=%s with Nuki Web "
        "(window=%ss, interval=%ss)",
        nuki_id, cfg.window_seconds, cfg.poll_interval_seconds,
    )
    deadline = mono + cfg.window_seconds
    attempt = 0
    while True:
        attempt += 1
        web_id = _resolve_web_id(payload, config)
        entries = await nuki_web.get_recent_log(smartlock_id=web_id, limit=20)
        match = _find_recent_user_open(
            entries, now=now_func(), recency_seconds=cfg.recency_seconds,
        )
        if match is not None:
            from nukiblinker.nuki_web_client import TRIGGER_NAMES
            trigger = match.get("trigger")
            context: dict = {"name": match["name"], "name_source": "web_api"}
            if trigger is not None:
                context["trigger"] = trigger
            logger.info(
                "Opener open correlated via Nuki Web for nukiId=%s: name=%s "
                "trigger=%s(%s) after %d poll(s)",
                nuki_id, match["name"], trigger,
                TRIGGER_NAMES.get(trigger, "unknown"), attempt,
            )
            # Cooldown so trailing status callbacks from the same open don't
            # trigger a second ring_to_open.
            _correlation_block_until[nuki_id] = time_func() + cfg.recency_seconds
            return context
        if time_func() >= deadline:
            break
        await sleep(cfg.poll_interval_seconds)

    logger.info(
        "No user open correlated in Nuki Web for nukiId=%s within %ss (%d poll(s))",
        nuki_id, cfg.window_seconds, attempt,
    )
    return None
