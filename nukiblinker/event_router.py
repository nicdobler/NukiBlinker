"""Classifies Nuki callback events and dispatches to the matching rule."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nukiblinker.logging_config import get_logger

if TYPE_CHECKING:
    from nukiblinker.config import AppConfig

logger = get_logger("event_router")

# Nuki Opener states (deviceType=2)
_OPENER_STATE_RING_TO_OPEN = 7  # opening
_OPENER_STATE_RING = 1  # online — ring detected, door stays closed

# Nuki Smart Lock states (deviceType=0)
_LOCK_STATE_UNLOCKED = 3
_LOCK_STATE_UNLATCHED = 5


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
        if state == _OPENER_STATE_RING:
            logger.info("Event classified: ring (Opener %s, state=%s)", nuki_id, state)
            return "ring"
        logger.debug("Ignoring Opener state %s (nukiId=%s)", state, nuki_id)
        return None

    if device_type == 0:  # Smart Lock
        if config.nuki.lock_id is not None and nuki_id != config.nuki.lock_id:
            logger.debug("Ignoring Smart Lock %s (filter: %s)", nuki_id, config.nuki.lock_id)
            return None
        if state in (_LOCK_STATE_UNLOCKED, _LOCK_STATE_UNLATCHED):
            logger.info("Event classified: door_opened (Lock %s, state=%s)", nuki_id, state)
            return "door_opened"
        logger.debug("Ignoring Smart Lock state %s (nukiId=%s)", state, nuki_id)
        return None

    logger.debug("Ignoring unknown deviceType %s", device_type)
    return None


async def resolve_person(payload: dict, nuki_client, fallback_name: str = "Alguien") -> dict:
    """Query Nuki Bridge /log to get the user name for the event.

    Returns context dict: {"name": "Nico"} or {"name": fallback}.
    """
    nuki_id = payload.get("nukiId")
    if nuki_id is None or nuki_client is None:
        return {"name": fallback_name}
    try:
        log_entry = await nuki_client.get_last_log(nuki_id)
        name = log_entry.get("name", "") if log_entry else ""
        if not name:
            name = fallback_name
        logger.info("Resolved person: %s (nukiId=%s)", name, nuki_id)
        return {"name": name}
    except Exception:
        logger.warning("Failed to resolve person for nukiId=%s — using fallback", nuki_id, exc_info=True)
        return {"name": fallback_name}


async def dispatch(event_type: str, payload: dict, config: AppConfig, clients) -> None:
    """Look up the event rule and fire matching notification channels."""
    from nukiblinker import notifier  # noqa: E402 — deferred to avoid circular import

    rule = getattr(config.events, event_type, None)
    if rule is None:
        logger.warning("No event rule for type '%s'", event_type)
        return

    context: dict = {}
    if event_type in ("ring_to_open", "door_opened"):
        fallback = rule.audio.fallback_name if rule.audio else "Alguien"
        context = await resolve_person(payload, getattr(clients, "nuki", None), fallback)

    logger.info("Dispatching event '%s' with context %s", event_type, context)
    await notifier.notify(rule, config, clients, context)
