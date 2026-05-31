# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Switched from GHCR image pull to local Docker build on Mini PC (`docker compose build`).
- CI pipeline now only runs lint + test; removed `build-and-push` job.
- Deploy/update scripts use `docker compose build` instead of `docker compose pull`.

### Added
- Config startup summary log: shows which integrations are configured on boot (e.g., `nuki=192.168.1.100, hue=<not configured>`).
- Config save verification: `save_config()` reads back written file and raises `IOError` if content doesn't match.
- Speaker logging: Chromecast and AirPlay clients now warn when no matching speakers are found during playback and log discovery count.
- Enhanced web UI: tabbed configuration interface (Status, Nuki, Hue, Speakers, HomeKit, Events).
  - Nuki: bridge discovery, callback registration, device listing with click-to-set IDs.
  - Hue: bridge discovery, guided pairing (press button → pair), light & group listing.
  - Speakers: Chromecast & AirPlay discovery, volume slider.
  - HomeKit: enable/disable toggle, setup code, persist directory.
  - Events: full per-event config — blink mode with custom HSB, audio (TTS/chime), HomeKit toggle.
  - Fixed save bar, mandatory field indicators, status badge in header.
- New API endpoints: `/api/nuki/pair`, `/api/nuki/devices`, `/api/nuki/callbacks`,
  `/api/hue/pair`, `/api/hue/lights`, `/api/hue/groups`.

### Fixed
- HomeKit startup log: `start()` now returns a boolean; success message only logged when HAP-python is available.
- Notifier: "no notification channels" message bumped from DEBUG to INFO for better diagnostics.
- `PUT /api/config` now preserves masked secrets (`***`) instead of overwriting real tokens.
- Docker: switched to `network_mode: host` — enables mDNS/multicast for speaker discovery, HomeKit, and direct LAN access to Nuki/Hue bridges.
- Migrated FastAPI `on_event("startup")`/`on_event("shutdown")` to `lifespan` context manager (fixes DeprecationWarning).
- Callback URL now auto-detects LAN IP when `server.host` is `0.0.0.0` instead of sending a literal `0.0.0.0` to the Nuki Bridge.
- Web UI middleware now allows all private-network IPs (not just localhost) — fixes 403 Forbidden when accessing via Docker bridge network.
- Added deployment manual and troubleshooting section to README.

### Changed
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
