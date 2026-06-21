"""FastAPI app — Nuki callback endpoint, health check, web UI mount."""

from __future__ import annotations

import time
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from nukiblinker import event_router
from nukiblinker.event_validator import ValidationResult
from nukiblinker.logging_config import get_logger

logger = get_logger("server")


def create_app(config, clients, lifespan=None) -> FastAPI:
    """Create and return the FastAPI application."""
    app = FastAPI(title="NukiBlinker", version="0.1.0", lifespan=lifespan)

    # Store references for use in routes
    app.state.config = config
    app.state.clients = clients
    app.state.paused = False
    app.state.last_event = None
    app.state.audio_files = {}  # filename -> Path mapping for /audio/ serving

    @app.post("/nuki/callback")
    async def nuki_callback(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
        """Receive Nuki Bridge callback and dispatch event."""
        if app.state.paused:
            logger.info("Callback received but service is paused — ignoring")
            return JSONResponse({"status": "paused"})

        try:
            payload: dict[str, Any] = await request.json()
        except Exception:
            logger.warning("Invalid callback payload")
            return JSONResponse({"error": "invalid payload"}, status_code=400)

        logger.info("Callback received: %s", payload)

        # Staleness guard: a fresh ring (ringactionState true) should carry a
        # near-instant ringactionTimestamp. A much older one is the only real
        # "strange hours" signal and hints at bridge buffering or clock drift.
        staleness = event_router.ringaction_staleness(payload)
        if staleness is not None and staleness > event_router.RINGACTION_STALE_THRESHOLD_S:
            logger.warning(
                "Fresh ring carries a stale ringactionTimestamp (%.0fs old, "
                "threshold %ds) — possible Bridge buffering or clock drift",
                staleness, event_router.RINGACTION_STALE_THRESHOLD_S,
            )

        # Event validation. Compute the result once and reuse it everywhere
        # (logging branches, dispatch) instead of recomputing per branch.
        if app.state.config.event_validation.enabled:
            validation_result = app.state.clients.event_validator.validate_event(payload)
            if not validation_result.valid:
                logger.warning("Event rejected by validation: %s", validation_result.reason)
                # Log the rejected event
                if app.state.config.event_log.enabled:
                    app.state.clients.event_log.log_event(
                        payload=payload,
                        event_type=None,
                        actions=[f"Rejected: {validation_result.reason}"],
                        validation_result=validation_result,
                        event_time=event_router.event_time_for_log(payload),
                    )
                return JSONResponse({"status": "rejected", "reason": validation_result.reason})
        else:
            validation_result = ValidationResult(
                valid=True, delay_seconds=0.0, reason="validation disabled"
            )

        # Classify event
        event_type = event_router.classify(payload, app.state.config)
        if event_type is None:
            # #219: Opener state=1 online or state=3 rto-active may carry an
            # app-triggered open ("Abierta"). Delegate to async web lookup.
            if event_router.is_opener_app_open_candidate(payload, app.state.config):
                nuki_web = getattr(app.state.clients, "nuki_web", None)
                if nuki_web is not None:
                    background_tasks.add_task(
                        _classify_and_dispatch_app_open,
                        payload,
                        app.state.config,
                        app.state.clients,
                        nuki_web,
                        validation_result,
                    )
                    return JSONResponse({"status": "pending", "reason": "web_lookup_app_open"})
            logger.info("Event ignored (no matching rule)")
            if app.state.config.event_log.enabled:
                app.state.clients.event_log.log_event(
                    payload=payload,
                    event_type=None,
                    actions=["Ignored: no matching rule"],
                    validation_result=validation_result,
                    event_time=event_router.event_time_for_log(payload),
                )
            return JSONResponse({"status": "ignored"})

        # #220: state=7 needs web disambiguation (RTO vs opener button).
        # Resolve synchronously in background so the 200 is returned instantly.
        if event_router.is_opener_state7_candidate(payload, app.state.config):
            nuki_web = getattr(app.state.clients, "nuki_web", None)
            if nuki_web is not None:
                background_tasks.add_task(
                    _classify_and_dispatch_state7,
                    payload,
                    app.state.config,
                    app.state.clients,
                    nuki_web,
                    validation_result,
                )
                return JSONResponse({"status": "pending", "reason": "web_lookup_state7"})
            # No web API — keep ring_to_open as-is, fall through to normal dispatch.

        # Deduplicate: one real interaction emits several callbacks (#97).
        deduplicator = getattr(app.state.clients, "deduplicator", None)
        if deduplicator is not None and deduplicator.is_duplicate(payload, event_type):
            window = app.state.config.deduplication.window_seconds
            logger.info("Duplicate %s event suppressed (within %ss)", event_type, window)
            if app.state.config.event_log.enabled:
                app.state.clients.event_log.log_event(
                    payload=payload,
                    event_type=event_type,
                    actions=[f"Suppressed: duplicate within {window}s"],
                    validation_result=validation_result,
                    event_time=event_router.event_time_for_log(payload),
                )
            return JSONResponse({"status": "duplicate", "event": event_type})

        app.state.last_event = {"type": event_type, "payload": payload}

        # Dispatch in background so we return 200 immediately
        background_tasks.add_task(
            _dispatch_with_logging,
            event_type,
            payload,
            app.state.config,
            app.state.clients,
            validation_result
        )

        return JSONResponse({"status": "ok", "event": event_type})

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "paused": app.state.paused})

    @app.get("/audio/{filename}")
    async def serve_audio(filename: str) -> FileResponse:
        """Serve audio files (TTS/chime) so speakers can stream them."""
        path = app.state.audio_files.get(filename)
        if path and path.exists():
            media_type = "audio/wav" if path.suffix == ".wav" else "audio/mpeg"
            return FileResponse(path, media_type=media_type)
        return JSONResponse({"error": "not found"}, status_code=404)

    return app


async def _dispatch_with_logging(event_type: str, payload: dict, config, clients, validation_result):
    """Dispatch event with logging and night mode support."""
    start_time = time.time()

    try:
        # Apply night mode if enabled
        rule = getattr(config.events, event_type)
        if config.night_mode.enabled:
            rule = clients.night_mode.apply_night_mode(rule)

        # Resolve the person here (Opener events only) so the matched Nuki Web
        # entry date is available both for dispatch and for logging the real
        # event time (#204). Passing it as context_override avoids a second
        # Web API round-trip inside dispatch_with_actions.
        context = None
        if event_type in ("ring", "ring_to_open"):
            fallback = rule.audio.fallback_name if rule.audio else "Alguien"
            context = await event_router.resolve_person(
                payload, fallback,
                nuki_web=getattr(clients, "nuki_web", None), config=config,
            )
        # apertura_con_app/apertura_opener: context already resolved by the
        # web-lookup background tasks; _dispatch_with_logging is only called for
        # the no-web-API fallback path where context stays None.

        # Dispatch the event
        actions = await event_router.dispatch_with_actions(
            event_type, payload, config, clients, rule, context_override=context
        )

        processing_time_ms = (time.time() - start_time) * 1000

        # Log the successful event with its real event time (#204)
        if config.event_log.enabled:
            clients.event_log.log_event(
                payload=payload,
                event_type=event_type,
                actions=actions,
                validation_result=validation_result,
                processing_time_ms=processing_time_ms,
                event_time=event_router.event_time_for_log(payload, context),
                nuki_web_response=context.get("nuki_web_response") if context else None,
            )

        logger.info("Event processed: %s -> %s (%.1fms)", event_type, actions, processing_time_ms)

    except Exception as e:
        processing_time_ms = (time.time() - start_time) * 1000

        # Log the error
        if config.event_log.enabled:
            clients.event_log.log_event(
                payload=payload,
                event_type=event_type,
                actions=[f"Error: {str(e)}"],
                validation_result=validation_result,
                processing_time_ms=processing_time_ms,
                event_time=event_router.event_time_for_log(payload),
                nuki_web_response=context.get("nuki_web_response") if context else None,
            )

        logger.error("Event processing failed: %s", e)


async def _classify_and_dispatch_state7(payload, config, clients, nuki_web, validation_result):
    """Background task: web-disambiguate state=7 then dispatch (#220).

    Queries the Nuki Web log to tell apart a Ring-to-Open (action=224) from a
    physical opener-button press (action=3), then dispatches the correct event.
    Falls back to ring_to_open when the Web API is unavailable or inconclusive.
    """
    event_type = await event_router.classify_state7_with_web(payload, config, nuki_web)
    logger.info("state=7 web-classified as: %s", event_type)

    rule = getattr(config.events, event_type, None)
    if rule is None:
        logger.warning("No event rule for type '%s' (state=7 web result)", event_type)
        return

    if config.night_mode.enabled:
        rule = clients.night_mode.apply_night_mode(rule)

    context: dict | None = None
    if event_type == "ring_to_open":
        fallback = rule.audio.fallback_name if rule.audio else "Alguien"
        context = await event_router.resolve_person(
            payload, fallback, nuki_web=nuki_web, config=config,
        )

    start_time = time.time()
    actions = await event_router.dispatch_with_actions(
        event_type, payload, config, clients, rule, context_override=context
    )
    processing_time_ms = (time.time() - start_time) * 1000

    if config.event_log.enabled:
        clients.event_log.log_event(
            payload=payload,
            event_type=event_type,
            actions=actions,
            validation_result=validation_result,
            processing_time_ms=processing_time_ms,
            event_time=event_router.event_time_for_log(payload, context),
            nuki_web_response=context.get("nuki_web_response") if context else None,
        )
    logger.info("Event processed: %s -> %s (%.1fms)", event_type, actions, processing_time_ms)


async def _classify_and_dispatch_app_open(payload, config, clients, nuki_web, validation_result):
    """Background task: detect app open via web log then dispatch (#219).

    Queries the Nuki Web log on an Opener state=1/state=3 callback. If a fresh
    "Abierta" entry (action=3) with a user name appears, dispatches
    apertura_con_app. Otherwise logs the callback as ignored (routine keepalive).
    """
    event_type, context = await event_router.classify_app_open_with_web(
        payload, config, nuki_web,
    )

    if event_type is None:
        logger.info("Event ignored (no matching rule) [post-web-lookup state=1/3]")
        if config.event_log.enabled:
            clients.event_log.log_event(
                payload=payload,
                event_type=None,
                actions=["Ignored: no matching rule"],
                validation_result=validation_result,
                event_time=event_router.event_time_for_log(payload),
            )
        return

    logger.info("state=1/3 web-classified as: %s (context=%s)", event_type, context)

    rule = getattr(config.events, event_type, None)
    if rule is None:
        logger.warning("No event rule for type '%s' (state=1/3 web result)", event_type)
        return

    if config.night_mode.enabled:
        rule = clients.night_mode.apply_night_mode(rule)

    start_time = time.time()
    actions = await event_router.dispatch_with_actions(
        event_type, payload, config, clients, rule, context_override=context
    )
    processing_time_ms = (time.time() - start_time) * 1000

    if config.event_log.enabled:
        clients.event_log.log_event(
            payload=payload,
            event_type=event_type,
            actions=actions,
            validation_result=validation_result,
            processing_time_ms=processing_time_ms,
            event_time=event_router.event_time_for_log(payload, context),
        )
    logger.info("Event processed: %s -> %s (%.1fms)", event_type, actions, processing_time_ms)
