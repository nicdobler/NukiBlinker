# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed
- **#106**: Removed the Apple HomePod / AirPlay 2 audio integration (`airplay_client.py`, `pyatv` dependency, `speakers.airplay` config field, AirPlay discovery, and the AirPlay card in the web UI). HomePod RTSP `SETUP` timed out unreliably and produced no audio; the masked `'set' object can't be awaited` warning behind it was the already-fixed #101 bug. HomePod owners are still notified via the HomeKit doorbell. Chromecast / Google Nest is now the only speaker audio channel. Existing `speakers.airplay` keys in `config.yaml` are ignored.

### Changed
- CI failure reporting now keeps a single issue per branch (deduplicated via a hidden marker) instead of opening a new issue on every failing commit, and auto-closes that issue when CI goes green again.

### Fixed
- **Code review**: Batch of bug fixes from a full-codebase review:
  - Web UI feature-config endpoints (`/api/config/event-validation|night-mode|event-log`) now persist to the launch `--config` path instead of a hardcoded `./config.yaml`, preventing config drift / lost changes in the Dockerized deploy.
  - `PUT /api/config` no longer wipes stored Nuki/Hue credentials when the request omits the `nuki`/`hue` sections (omitted sections are preserved like masked secrets).
  - Event deduplication no longer collapses two genuinely distinct `ring_to_open`/`door_opened` events: the discriminator now prefers a per-event `timestamp` (falling back to `state` for burst suppression when no timestamp is present).
  - Chromecast name-based playback no longer leaks a `Zeroconf`/`CastBrowser` per event, and cast socket clients are now disconnected after playback; `volume_level == None` is handled when saving/restoring volume.
  - Event-log CSV export now renders a `0.00` ms processing time instead of a blank cell, and the temporary CSV file is deleted after the response is sent.
  - `/api/test/event` now mirrors the real pipeline (applies night mode and records the event in the Event Log).
  - Hue custom-blink restore honours the light's original colour mode (`ct`/`xy`/`hs`) instead of forcing it into hue/sat.
  - Night mode grace period now wraps correctly across midnight (minutes-of-day arithmetic).
  - Server computes the validation result once per callback and reuses it across logging branches.
- **#101**: AirPlay playback logged `'set' object can't be awaited` and the real playback error was hidden. `pyatv`'s `AppleTV.close()` is synchronous and returns a `Set[asyncio.Task]`, so it must not be awaited — it is now called without `await`.
- **#97**: A single real interaction fired multiple notifications. Opener `state == 1` ("online") was misclassified as a ring — rings are now detected from `ringactionState`/`ringactionTimestamp`. Added event deduplication (default 120 s window) that collapses the burst of callbacks one interaction emits while still letting a genuine second ring through.
- **#96**: Event-log CSV export now opens cleanly in Excel (UTF-8 BOM + `sep=,` hint), shows timestamps in a configurable local timezone split into `Date`/`Time` columns, and can be filtered by device.
- **#89, #91, #92, #93**: QR code generation failed with "missing required positional argument: 'file'" — now captures `pyqrcode` SVG output via `io.BytesIO` and decodes it, and defensively handles `base36.dumps()` and the driver's `setup_id` returning either `bytes` or `str`
- HomeKit accessory silently dropped by iOS right after a successful pairing: the `StatelessProgrammableSwitch` now carries `ServiceLabelIndex=1` to disambiguate the two `ProgrammableSwitchEvent` services, and the Doorbell is marked as primary service
- HomeKit "incorrect setup code": auto-generated setup codes are now persisted in `persist_dir/setup_code` and reused across restarts (previously a new random code was logged on every start while HAP-python kept the original pincode), and generation skips the trivial codes Apple rejects
- HomeKit pairing failures: accessory category changed from `VIDEO_DOOR_BELL` to `SENSOR` (iOS rejects video doorbells without a camera stream), and the HAP driver now binds/advertises on the LAN IP resolved by `server.public_host` / auto-detect instead of letting zeroconf pick an interface

### Added
- **Docs**: Added architecture diagrams to `specs/tech-spec.md` — a component diagram (external systems + internal modules), a class diagram (`Clients` container and service clients), and a callback processing pipeline sequence diagram.
- **Docs**: Added a Documentation index to `README.md` linking the product/tech specs, changelog, config template, and deploy notes.
- **Docs**: Aligned specs and README with the code — corrected the default chime to `chime.wav` (generated at Docker build) and the base image to `python:3.14-slim`; added `server.public_host` and removed the non-existent `homekit.address` from the tech-spec config model; clarified that event validation and night mode are global (not per-event); documented the `GET /api/homekit/qr` endpoint; and completed the test-suite table.
- **#97**: The resolved action `trigger` (e.g. `Trigger: button (2)`) is now surfaced in the Event Log / CSV for `ring_to_open` and `door_opened` events, and is captured even for anonymous opens. This lets you confirm exactly which trigger code a physical-button open produces before deciding which triggers to suppress (suppression itself is not yet wired).
- Optional **Nuki Web API** integration (`nuki.web_api_token`): when configured, resolves real user names and the action `trigger`/`source` from the cloud activity log (the local bridge cannot identify an anonymous ringer). Read-only — it never opens or locks doors.
- Event deduplication config (`deduplication.enabled`, `deduplication.window_seconds`).
- Event-log CSV timezone config (`event_log.timezone`, default `Europe/Madrid`) and device filtering in the Event Log viewer and export. New endpoint `/api/events/devices`; `/api/events/log` and `/api/events/export` accept `?device_id=`.
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
