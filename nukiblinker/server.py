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
            logger.info("Event ignored (no matching rule)")
            # Log the ignored event
            if app.state.config.event_log.enabled:
                app.state.clients.event_log.log_event(
                    payload=payload,
                    event_type=None,
                    actions=["Ignored: no matching rule"],
                    validation_result=validation_result,
                    event_time=event_router.event_time_for_log(payload),
                )
            # #219/#220 discovery probe (log-only, no dispatch/notify): on an
            # Opener `state=1 online` callback, capture the Nuki Web signal that
            # accompanies an app-triggered open ("Abierta") so the real codes can
            # be confirmed before wiring the classification.
            if event_router.is_opener_status_probe_candidate(payload, app.state.config):
                background_tasks.add_task(
                    event_router.discovery_probe_app_open,
                    payload,
                    app.state.config,
                    app.state.clients,
                )
            return JSONResponse({"status": "ignored"})

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
            )

        logger.error("Event processing failed: %s", e)
