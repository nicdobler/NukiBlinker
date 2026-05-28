# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Project scaffolding: specs, config, Dockerfile, Makefile, CI setup.
- Core implementation: all modules, tests, and web UI.
  - `config.py` — Pydantic models with full event rules, load/save YAML.
  - `server.py` — FastAPI callback endpoint, health check.
  - `event_router.py` — Event classification (ring, ring_to_open, door_opened) + person resolution via Nuki `/log`.
  - `nuki_client.py` — Nuki Bridge API (callbacks, devices, activity log).
  - `hue_client.py` — Hue Bridge v1 REST (alert, custom blink, pairing).
  - `audio.py` — TTS generation (gTTS) + chime selection + `{name}` template rendering.
  - `chromecast_client.py` — Google Nest / Chromecast audio playback.
  - `airplay_client.py` — Apple HomePod / AirPlay 2 audio playback.
  - `homekit_service.py` — Virtual HomeKit doorbell accessory (HAP-python).
  - `notifier.py` — Orchestrates all notification channels per event rule.
  - `discovery.py` — Auto-discovery for Nuki, Hue, Chromecast, AirPlay.
  - `web_ui.py` — Localhost-only config API + static SPA.
  - `__main__.py` — Entry point with startup/shutdown lifecycle.
  - `static/index.html` — Web UI SPA (dark theme, vanilla JS).
  - Full test suite: 12 test files covering all modules.
