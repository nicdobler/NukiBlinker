"""FastAPI app — Nuki callback endpoint, health check, web UI mount."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from nukiblinker import event_router
from nukiblinker.logging_config import get_logger

logger = get_logger("server")


def create_app(config, clients) -> FastAPI:
    """Create and return the FastAPI application."""
    app = FastAPI(title="NukiBlinker", version="0.1.0")

    # Store references for use in routes
    app.state.config = config
    app.state.clients = clients
    app.state.paused = False
    app.state.last_event = None

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

        event_type = event_router.classify(payload, app.state.config)
        if event_type is None:
            logger.debug("Event ignored (no matching rule)")
            return JSONResponse({"status": "ignored"})

        app.state.last_event = {"type": event_type, "payload": payload}

        # Dispatch in background so we return 200 immediately
        background_tasks.add_task(event_router.dispatch, event_type, payload, app.state.config, app.state.clients)

        return JSONResponse({"status": "ok", "event": event_type})

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "paused": app.state.paused})

    return app
