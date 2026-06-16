"""Classifies Nuki callback events and dispatches to the matching rule."""

from __future__ import annotations

import asyncio
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

# Person resolution retry — the bridge log lags behind the callback
_RESOLVE_PERSON_ATTEMPTS = 3
_RESOLVE_PERSON_RETRY_SECONDS = 1.0


def classify(payload: dict, config: AppConfig) -> str | None:
    """Return event type string or None if the payload should be ignored.

    Possible return values: 'ring', 'ring_to_open', 'door_opened'.
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
        logger.info(
            "Opener callback ignored: state=%s nukiId=%s ringactionState=%s "
            "ringactionTimestamp=%s — full payload: %s",
            state, nuki_id, payload.get("ringactionState"),
            payload.get("ringactionTimestamp"), payload,
        )
        return None

    if device_type == 0:  # Smart Lock
        if config.nuki.lock_id is not None and nuki_id != config.nuki.lock_id:
            logger.debug("Ignoring Smart Lock %s (filter: %s)", nuki_id, config.nuki.lock_id)
            return None
        if state in (_LOCK_STATE_UNLATCHED, _LOCK_STATE_UNLATCHING):
            logger.info("Event classified: door_opened (Lock %s, state=%s)", nuki_id, state)
            return "door_opened"
        logger.debug("Ignoring Smart Lock state %s (nukiId=%s)", state, nuki_id)
        return None

    logger.debug("Ignoring unknown deviceType %s", device_type)
    return None


async def resolve_person(payload: dict, nuki_client, fallback_name: str = "Alguien",
                         nuki_web=None) -> dict:
    """Resolve the user name (and trigger) for the event.

    Resolution order:
    1. Nuki Web API (when configured) — reliably returns ``name``/``trigger``.
    2. Nuki Bridge ``/log`` — best-effort, with retry (the bridge writes the log
       slightly after firing the callback). May have no name for anonymous rings.

    Returns context dict: {"name": "Nico", "name_source": ...} (plus "trigger"
    when known). ``name_source`` is one of "web_api", "bridge_log" or
    "fallback" — the last meaning no identity was resolved (e.g. an anonymous
    Ring-to-Open), which is expected, not a failure (#155).
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

    # 1. Nuki Web API — preferred when available (real names + trigger source).
    if nuki_web is not None:
        try:
            from nukiblinker.nuki_web_client import TRIGGER_NAMES, SOURCE_DOOR_SENSOR

            entries = await nuki_web.get_recent_log(smartlock_id=nuki_id, limit=20)
            if entries:
                # The most recent entry is the best candidate, but door-sensor
                # entries (source=SOURCE_DOOR_SENSOR) carry no name and arrive
                # immediately after an open, pushing the real named entry down
                # the list (#157). Capture the trigger from the most recent
                # entry, then find the first named entry within a short window
                # (skipping anonymous sensor entries).
                most_recent = entries[0]
                resolved_trigger = most_recent.get("trigger")

                # Skip leading door-sensor entries (source=SOURCE_DOOR_SENSOR):
                # these carry no name and arrive immediately after the opener's
                # own event, pushing the real named entry down the list (#157).
                # Stop skipping at the first non-sensor entry — if that entry
                # has no name, the open is genuinely anonymous (e.g. an RTO
                # with no user identity) and we must not look further (#155).
                first_non_sensor = next(
                    (e for e in entries if e.get("source") != SOURCE_DOOR_SENSOR),
                    None,
                )
                candidate = first_non_sensor if first_non_sensor is not None else most_recent
                name = candidate.get("name")
                trigger_for_log = candidate.get("trigger")
                if trigger_for_log is None:
                    trigger_for_log = resolved_trigger
                else:
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
                # Anonymous open: surface the trigger for observability (#97)
                # but fall back to the bridge log for a name.
                logger.info(
                    "Web API: no name found for nukiId=%s (checked %d entries, "
                    "first_non_sensor=%s); trigger=%s(%s) — falling back to bridge log",
                    nuki_id,
                    len(entries),
                    first_non_sensor is not None,
                    resolved_trigger,
                    TRIGGER_NAMES.get(resolved_trigger, "unknown"),
                )
            else:
                logger.info("Nuki Web API log empty for nukiId=%s — falling back to bridge log", nuki_id)
        except Exception:
            logger.warning("Nuki Web API resolution failed — falling back to bridge log", exc_info=True)

    if nuki_id is None or nuki_client is None:
        return _result(fallback_name, "fallback")
    try:
        name = ""
        # The bridge writes the activity log slightly after firing the
        # callback — retry briefly so the user name is available (#60).
        for attempt in range(_RESOLVE_PERSON_ATTEMPTS):
            log_entry = await nuki_client.get_last_log(nuki_id)
            logger.debug("Log entry for nukiId=%s (attempt %d): %s", nuki_id, attempt + 1, log_entry)
            name = log_entry.get("name", "") if log_entry else ""
            if name:
                break
            if attempt < _RESOLVE_PERSON_ATTEMPTS - 1:
                await asyncio.sleep(_RESOLVE_PERSON_RETRY_SECONDS)
        if not name:
            logger.warning(
                "No name in bridge log for nukiId=%s after %d attempts — using fallback",
                nuki_id, _RESOLVE_PERSON_ATTEMPTS,
            )
            return _result(fallback_name, "fallback")
        logger.info("Resolved person: %s (nukiId=%s)", name, nuki_id)
        return _result(name, "bridge_log")
    except Exception:
        logger.warning("Failed to resolve person for nukiId=%s — using fallback", nuki_id, exc_info=True)
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
    elif event_type in ("ring_to_open", "door_opened"):
        fallback = rule.audio.fallback_name if rule.audio else "Alguien"
        context = await resolve_person(
            payload, getattr(clients, "nuki", None), fallback,
            nuki_web=getattr(clients, "nuki_web", None),
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
    elif event_type in ("ring_to_open", "door_opened"):
        fallback = rule.audio.fallback_name if rule.audio else "Alguien"
        context = await resolve_person(
            payload, getattr(clients, "nuki", None), fallback,
            nuki_web=getattr(clients, "nuki_web", None),
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
