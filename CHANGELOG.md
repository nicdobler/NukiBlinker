# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **#89**: QR code generation failed with "missing required positional argument: 'file'" — now uses `io.StringIO` to capture SVG output as a string
- HomeKit accessory silently dropped by iOS right after a successful pairing: the `StatelessProgrammableSwitch` now carries `ServiceLabelIndex=1` to disambiguate the two `ProgrammableSwitchEvent` services, and the Doorbell is marked as primary service
- HomeKit "incorrect setup code": auto-generated setup codes are now persisted in `persist_dir/setup_code` and reused across restarts (previously a new random code was logged on every start while HAP-python kept the original pincode), and generation skips the trivial codes Apple rejects
- HomeKit pairing failures: accessory category changed from `VIDEO_DOOR_BELL` to `SENSOR` (iOS rejects video doorbells without a camera stream), and the HAP driver now binds/advertises on the LAN IP resolved by `server.public_host` / auto-detect instead of letting zeroconf pick an interface

### Added
- HomeKit accessory now exposes a `StatelessProgrammableSwitch` alongside the Doorbell service, so rings can trigger Home app automations (assign scenes/actions to the button's single press)
- **#56**: Night mode - configurable quiet hours with reduced notifications (no audio, dimmer lights)
- **#57**: Event log viewer - comprehensive event history with detailed action tracking and CSV export
- **#59**: Event timestamp validation - configurable validation to reject stale events
- Event validation service with configurable delay threshold (default: 60 seconds)
- Event logging service with in-memory storage, file persistence, and cleanup
- Night mode service with time-based notifications and grace periods
- New web UI "Event Log" tab for viewing event history with pagination
- New configuration sections in Events tab for validation, night mode, and logging
- Enhanced event pipeline with detailed action tracking and processing times
- New API endpoints: `/api/events/log`, `/api/events/export`, `/api/events/clear`
- New configuration endpoints: `/api/config/event-validation`, `/api/config/night-mode`, `/api/config/event-log`
- Thread-safe event logging with concurrent access support
- CSV export functionality for event analysis
- Real-time night mode status indicators in web UI
- Event validation with graceful handling of missing/future timestamps

### Changed
- Enhanced notifier to return detailed action results for logging
- Updated event router to support validation and night mode integration
- Modified server callback handler to include event validation and logging
- Improved error handling throughout the event pipeline
- Enhanced web UI save/load to include new feature configurations

### Fixed
- **#73**: Event log API returned 500 — `event_log`, `event_validator` and `night_mode` services are now instantiated in the clients container at startup.
- **#74**: Web UI config neither loaded nor saved — removed infinite recursion caused by duplicate `loadConfig`/`saveConfig` declarations in `index.html`.
- **#72/#35**: HomeKit failed to initialize — fixed imports against the real HAP-python API (`CATEGORY_VIDEO_DOOR_BELL`, `add_preload_service`) and kept the `XXX-XX-XXX` pincode format.
- **#60**: Unlocking the Smart Lock without opening no longer fires `door_opened` (state 3 removed from classification; only state 5 unlatched triggers it). Person name resolution now retries briefly to compensate for bridge log lag.
- **#35**: AirPlay audio now plays correctly on HomePod — fixed missing `await` on `atv.close()` and added playback completion wait.
- **#38**: Hue groups now blink correctly in custom blink mode — `trigger_custom_blink()` now accepts and processes `group_ids` parameter.

### Changed
- Switched from GHCR image pull to local Docker build on Mini PC (`docker compose build`).
- CI pipeline now only runs lint + test; removed `build-and-push` job.
- Deploy/update scripts use `docker compose build` instead of `docker compose pull`.

### Added
- Config startup summary log: shows which integrations are configured on boot (e.g., `nuki=192.168.1.100, hue=<not configured>`).
- Config save verification: `save_config()` reads back written file and raises `IOError` if content doesn't match.
- Speaker logging: Chromecast and AirPlay clients now warn when no matching speakers are found during playback and log discovery count.
- Speaker IP connections: speakers can be configured by IP address instead of name, bypassing mDNS/zeroconf entirely. Chromecast uses `get_chromecast_from_host()`; AirPlay uses unicast `pyatv.scan(hosts=[ip])`.
- Graceful zeroconf error handling: port 5353 conflicts no longer crash discovery or playback — clear warnings are logged with guidance to use IPs.
- Silenced verbose third-party loggers (httpx, pychromecast, zeroconf, casttube, pyatv) — only warnings and errors from libraries.
- Improved default chime: longer ding-dong with harmonics for natural bell timbre.
- Better TTS diagnostics: logs file size on success, internet requirement on failure.
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
