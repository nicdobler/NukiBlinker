# Tasks

---

## #97 (follow-up) Surface the real trigger code for physical-button opens

**Branch**: `fix/97-trigger-observability` | **PR**: _pending_

Context: User reports a single real interaction (ring + open from upstairs) fires
multiple notifications, and that opening via the physical button should do
nothing. The dedup + ring reclassification fix (`f633adb`) already reduces the
multi-ring burst, but it shipped AFTER the CSV the user attached (events 15:51
+0200 < fix 18:21 +0200), so that part needs re-testing on the deployed build.
Physical-button suppression was deliberately deferred pending the user
confirming the real trigger code. User chose: confirm the trigger first, no
suppression yet.

- [x] `resolve_person`: capture + log `trigger` even for anonymous opens (no named entry), preserving bridge-log name fallback
- [x] `dispatch_with_actions`: prepend `Trigger: <name> (<code>)` to Event Log actions when a trigger is resolved
- [x] Tests: resolve_person trigger surfacing (bridge name + fallback), dispatch action injection / absence
- [x] Docs: CHANGELOG `[Unreleased]`
- [ ] Mac/CI: `make test` + `make lint` (not run on work laptop)
- [ ] User: open the door via the physical button, read `Trigger: ...` in the Event Log/CSV, report the code
- [ ] Decide & wire suppression for the confirmed trigger code(s)
- [ ] Open PR

Decisions:
- Trigger is surfaced via the Event Log `Actions` column (no schema/CSV-column
  change) — minimal, immediately visible where the user already reads events.
- Requires `nuki.web_api_token` configured; without it the bridge log has no
  reliable trigger and nothing is surfaced.

---

## #96 Event log CSV export & #97 multiple events per interaction

**Branch**: `fix/event-log-and-opener-events` | **PR**: _pending_

Context: `docs/nuki-bridge-api-1.13.3.md` confirms the Opener signals a ring via
`ringactionState`/`ringactionTimestamp`, not `state`. The bridge `/log` cannot
identify an anonymous visitor — the Nuki Web API can (names + trigger).

- [x] Spec gate: update product-spec & tech-spec (ring detection, dedup, CSV, Web API; amend Cloud-API non-goal)
- [x] Config: `nuki.web_api_token`, `event_log.timezone`, `deduplication` section
- [x] #96 CSV export: UTF-8 BOM + `sep=,` hint, local-tz Date/Time columns, device filter
- [x] #96 Event Log viewer device dropdown + `/api/events/devices`; `?device_id=` on log/export
- [x] #97 Reclassify Opener ring via `ringactionState` (removed `state==1 → ring`)
- [x] #97 `Deduplicator` (key includes `ringactionTimestamp` so double rings pass, bursts collapse); wired into callback
- [x] Optional `NukiWebClient` + `resolve_person` uses it first (name + trigger), bridge `/log` fallback
- [x] Tests: classify, dedup, web client, CSV (BOM/tz/device), web UI device endpoints/filter, server dedup
- [x] Docs: README, CHANGELOG, config.example.yaml, specs
- [ ] Mac/CI: `make test` + `make lint` (not run on work laptop)
- [ ] Open PR

Decisions:
- Dedup window default 120 s. Double-ring passthrough achieved by including
  `ringactionTimestamp` in the dedup key.
- Physical-button suppression NOT auto-applied: the Web API `trigger` is logged
  so the user can confirm the real code before any suppression is wired.

---

## Project Setup

**Branch**: `chore/project-setup`

- [x] Create project scaffolding (Agents.md, pyproject.toml, Makefile, .gitignore, Dockerfile)
- [x] Write product spec (specs/product-spec.md)
- [x] Write tech spec (specs/tech-spec.md)
- [x] Create workflows (.windsurf/workflows/*.md)
- [x] Create README.md and CHANGELOG.md
- [x] Create example config (config.example.yaml)
- [x] User approval of specs
- [ ] `poetry install` + verify tooling works (Mac)

---

## Core Implementation

**Branch**: `feat/core-implementation` | **PR**: TBD

### Phase 1 — Foundation (no external deps beyond FastAPI/httpx)
- [x] 1. `logging_config.py` — structured logging setup
- [x] 2. `config.py` — Pydantic models + load/save YAML
- [x] 3. `tests/test_config.py` — validation, defaults, load, save
- [x] 4. `event_router.py` — classify() + resolve_person() + dispatch()
- [x] 5. `tests/test_event_router.py` — all 3 event types + person resolution
- [x] 6. `nuki_client.py` — Nuki Bridge HTTP API (callbacks, devices, log)
- [x] 7. `tests/test_nuki_client.py` — mock httpx
- [x] 8. `hue_client.py` — Hue Bridge v1 REST (alert, custom blink, list)
- [x] 9. `tests/test_hue_client.py` — mock httpx

### Phase 2 — Audio & Speakers
- [x] 10. `audio.py` — TTS generation + chime + {name} template
- [x] 11. `tests/test_audio.py` — template, TTS mock, chime resolution
- [x] 12. `chromecast_client.py` — play audio on Chromecast speakers
- [x] 13. `tests/test_chromecast.py` — mock pychromecast
- [x] 14. `airplay_client.py` — play audio on AirPlay/HomePod speakers
- [x] 15. `tests/test_airplay.py` — mock pyatv

### Phase 3 — HomeKit & Notifier
- [x] 16. `homekit_service.py` — HAP-python doorbell accessory
- [x] 17. `tests/test_homekit.py` — mock HAP-python
- [x] 18. `notifier.py` — orchestrate channels per event rule
- [x] 19. `tests/test_notifier.py` — dispatch + failure isolation

### Phase 4 — Server & Web UI
- [x] 20. `server.py` — FastAPI callback endpoint + health
- [x] 21. `tests/test_server.py` — callback routing
- [x] 22. `discovery.py` — auto-discovery for all devices
- [x] 23. `tests/test_discovery.py` — mock zeroconf
- [x] 24. `web_ui.py` — API routes + localhost guard
- [x] 25. `tests/test_web_ui.py` — routes + 403 access control

### Phase 5 — Entry Point & Lifecycle
- [x] 26. `__main__.py` — startup, shutdown hook, pause/resume
- [x] 27. `tests/test_lifecycle.py` — startup, shutdown, pause/resume
- [x] 28. `static/index.html` — web UI SPA
- [x] 29. Update `config.example.yaml`, `pyproject.toml` deps, `Dockerfile`
- [x] 30. Update `README.md`, `CHANGELOG.md`

### Next
- [ ] `poetry install` + `make test` + `make lint` on Mac
- [ ] Fix any test/lint issues
- [ ] Open PR to main

---

## Fix open bugs (#60, #72, #73, #74; closes #35, #62–#70)

**Branch**: `fix/open-bugs` | **PR**: TBD

- [x] #73 — `_build_clients` now instantiates `event_log`, `event_validator`, `night_mode` (root cause: services referenced by `server.py`/`web_ui.py` but never built; tests passed because they mock `Clients`).
- [x] #74 — `index.html` had duplicate `loadConfig`/`saveConfig` declarations; the "enhanced" versions referenced `window.loadConfig` (themselves) → infinite recursion. Renamed base functions to `loadBaseConfig`/`saveBaseConfig`.
- [x] #72/#35 — `homekit_service.py` imported `CATEGORY_DOORBELL` and `pyhap.loader.get_serv_loader`, neither of which exist in HAP-python. Switched to `CATEGORY_VIDEO_DOOR_BELL` + `add_preload_service("Doorbell")`; pincode keeps `XXX-XX-XXX` format.
- [x] #60 — Smart Lock state 3 (unlocked) removed from `door_opened` classification (only state 5 unlatched). `resolve_person` retries up to 3× (1s) when the bridge log lags.
- [x] Regression tests: `test_event_router.py`, `test_homekit.py`, `test_lifecycle.py`, `test_server.py`.
- [x] Docs: CHANGELOG, tech-spec (state table + flowchart).
- [ ] Verify on Mac/CI (`make test` + `make lint`), merge PR, close issues.

**Decisions**: #62–#70 are CI-autogenerated failure issues for PR #61 (merged, main CI green) — closed without code changes.

---

## Fix HomeKit pairing failure (lessons from Homebridge)

**Branch**: `fix/homekit-pairing` | **PR**: #79

- [x] Diagnose: discovery fixed by firewall (UDP 5353); pairing still failed
- [x] Change accessory category VIDEO_DOOR_BELL -> SENSOR (iOS rejects video doorbell without camera stream)
- [x] Bind HAP driver to explicit LAN address via `get_public_host()` (reuses `server.public_host`) - Homebridge `bind` pattern
- [x] Removed redundant `homekit.address` option after user review - reuse existing `server.public_host`
- [x] Regression tests (address bind, auto address, category)
- [x] Docs: tech-spec, README troubleshooting (TCP 51826, advertised IP, stale state), CHANGELOG, config.example.yaml
- [ ] Validate on Mac (`make test` + `make lint`)
- [ ] User confirms pairing works on Mini PC

---

## Fix HomeKit incorrect setup code

**Branch**: `fix/homekit-setup-code` | **PR**: pending

- [x] Root cause: random setup code regenerated on every restart while HAP-python persists the original pincode in accessory.state -> logged code != accepted code
- [x] Persist generated code to `{persist_dir}/setup_code` and reuse across restarts
- [x] Skip Apple-forbidden trivial codes (000-00-000..., 123-45-678, 876-54-321) in generation and persisted-code validation
- [x] Regression tests (persistence, precedence, forbidden re-roll); tests isolated to tmp_path
- [x] Docs: tech-spec, README troubleshooting, CHANGELOG
- [ ] Validate on Mac (`make test` + `make lint`), merge
- [ ] User pairs successfully on Mini PC

---

## HomeKit automation trigger (StatelessProgrammableSwitch)

**Branch**: `feat/homekit-automation-switch` | **PR**: pending

- [x] Add StatelessProgrammableSwitch service alongside Doorbell (Homebridge pattern - bare Doorbell events cannot trigger Home app automations)
- [x] trigger_ring() fires ProgrammableSwitchEvent on both services
- [x] Tests updated (both services preloaded, ring fires twice, missing service no-crash)
- [x] Docs: tech-spec, README features, CHANGELOG
- [ ] Validate on Mac (`make test` + `make lint`), merge
- [ ] User creates automation in Home app (may need to remove/re-add accessory to see the new button)

---

## Fix QR code generation (#89) + follow-up (#91, #92, #93)

**Branch**: `fix/qr-code-generation` | **PR**: #90

- [x] Root cause: `pyqrcode.svg()` requires a `file` parameter, but code called it without one
- [x] Fix: Use `io.StringIO()` to capture SVG output as a string
- [x] Regression tests: `test_generates_svg_string`, `test_uses_setup_id_from_driver_state`
- [x] Docs: CHANGELOG updated
- [x] Follow-up #91: `base36.dumps()` returns bytes in some versions, need to decode to string
- [x] Follow-up #92: `setup_id` from driver state can also be bytes, need to decode
- [x] Follow-up #93: pyqrcode writes bytes via `write_bytes()`, need `BytesIO` not `StringIO`
- [ ] Validate on Mac (`make test` + `make lint`)
- [ ] Merge PR, close issue #89, #91, #92, and #93

---

## Fix HomeKit accessory dropped after pairing

**Branch**: `fix/homekit-service-label` | **PR**: pending

- [x] Root cause: two ProgrammableSwitchEvent services without ServiceLabelIndex -> iOS pairs, then rejects attribute DB and drops the accessory
- [x] Add ServiceLabelIndex=1 to StatelessProgrammableSwitch; mark Doorbell as primary service
- [x] Regression test (chars kwarg, configure_char, is_primary_service)
- [x] Docs: tech-spec, CHANGELOG; lesson captured in lessons.md
- [ ] Validate on Mac, merge, deploy, clear ./homekit/*, re-pair, verify accessory persists in Home

---

## Fix #101 AirPlay "'set' object can't be awaited"

**Branch**: `fix/101-airplay-close-not-awaitable` | **PR**: pending

- [x] Root cause: `await atv.close()` in airplay_client.py — pyatv `AppleTV.close()` is sync and returns `Set[asyncio.Task]`, not awaitable. The TypeError masked the real playback error (HomePod SETUP TimeoutError).
- [x] Fix: call `atv.close()` without `await`
- [x] Regression test `test_close_is_not_awaited_regression` (close returns a set); fixed two existing tests that asserted `close` was awaited
- [x] CHANGELOG updated under [Unreleased]
- [ ] Validate on Mac (`make test` + `make lint`)
- [ ] Merge PR, close issue #101
- Note: #97 (multiple events) left out of scope per user decision — separate effort.

---

## #106 Remove AirPlay / HomePod integration

**Branch**: `chore/remove-airplay` | **PR**: _pending_

Context: #106 reported `'set' object can't be awaited` in the logs. Diagnosis:
that was the already-fixed #101 bug (logs predate commit `acce574`). The real
remaining symptom was **no AirPlay audio** — the HomePod "Salon" timed out on
RTSP `SETUP`. User decided to **remove the AirPlay integration entirely**;
HomePod still receives the ring via the HomeKit doorbell, and Google Nest covers
speaker audio.

- [x] Specs updated first (product-spec, tech-spec) — AirPlay/HomePod/pyatv removed
- [x] Deleted `nukiblinker/airplay_client.py` and `tests/test_airplay.py`
- [x] Removed AirPlay from `__main__.py` (Clients), `notifier.py`, `discovery.py`, `config.py` (SpeakersConfig.airplay + summary), `logging_config.py`, `web_ui.py`
- [x] Web UI: removed AirPlay card + load/save/discovery JS (also restored an accidentally-removed `populateEventRule('ring')` line)
- [x] Removed `pyatv` from `pyproject.toml`; removed `speakers.airplay` from `config.example.yaml`
- [x] Updated tests: test_discovery, test_notifier, test_lifecycle, test_server, test_web_ui, test_integration_event_pipeline
- [x] README, deploy/README, CHANGELOG updated
- [ ] **Mac/CI**: run `poetry lock` (poetry.lock still references pyatv), then `make test` + `make lint`
- [ ] Merge PR, close issue #106

---

## Code-review fixes (full-codebase bug hunt)

**Branch**: `fix/review-observations` | **PR**: _pending_

Context: Ran `/review` over the whole codebase, then `/fix-bug` for all findings.
Pure bug fixes — no spec changes required (Agents.md §0 "When to skip").

Fixes applied:
- [x] **#1 (high)** `web_ui.py`: 3 feature-config endpoints saved to hardcoded `"config.yaml"` instead of `app.state.config_path` → config drift in Docker deploy. Now use `config_path`.
- [x] **#2 (high)** `web_ui.py` `put_config`: partial PUT omitting `nuki`/`hue` wiped credentials. Omitted sections now preserved from current config.
- [x] **#3 (med)** `deduplication.py`: non-ring discriminator was constant `state`, collapsing distinct opens. Now prefers per-event `timestamp`, falls back to `state`.
- [x] **#4 (med)** `chromecast_client.py`: `Zeroconf`/`CastBrowser` leaked per event; cast clients never disconnected. Added per-call cleanup + `volume_level is None` guard.
- [x] **#5 (low)** `event_log.py`: CSV `processing_time_ms == 0.0` rendered blank (falsy). Now `is not None`.
- [x] **#6 (low)** `web_ui.py`: CSV export temp file leaked. Deleted via `BackgroundTask(os.unlink, ...)`.
- [x] **#7 (low)** `web_ui.py` `test_event`: bypassed night mode + event log. Now mirrors the real pipeline.
- [x] **Obs** `hue_client.py`: restore now honours `colormode` (`ct`/`xy`/`hs`).
- [x] **Obs** `night_mode.py`: grace period wraps across midnight (minutes-of-day arithmetic).
- [x] **Obs** `server.py`: `validation_result` computed once and reused.

Regression tests added: `test_deduplication.py` (timestamp discriminator), `test_night_mode.py` (midnight wrap), `test_hue_client.py` (ct restore), `test_event_log.py` (0.00 ms), `test_server.py` (validation disabled), `test_web_ui.py` (secret preservation + dispatch_with_actions), `test_web_ui_new_endpoints.py` (config_path persistence + test_event logging), `test_chromecast.py` (cleanup/disconnect).

- [x] `python -m py_compile` clean on all changed files (work-laptop syntax check only)
- [ ] **Mac/CI**: run `make test` + `make lint` (not run on Windows work laptop)
- [ ] Open PR, verify green, merge

---

## Event log: slow load + lost between versions → SQLite backend

**Branch**: `feat/event-log-sqlite` | **PR**: _pending_

Context: User reported the event log takes long to load and is lost between app
versions. Root causes: (1) `logs/` was never mounted as a volume → wiped on every
`docker compose build`; (2) JSON backend rewrote the whole file on every event
and parsed it all at startup. Chosen solution (user approved): embedded SQLite on
a mounted volume — no extra container. Spec-first per Agents.md §0.

- [x] Spec: `tech-spec.md` (SQLite data model, schema, query mapping, migration, docker volume) + `product-spec.md` (storage + Unreleased feature)
- [ ] `event_log.py`: SQLite backend, same public API, `entries` read property, `store_entry()`, legacy `.json` auto-migration to `.db`
- [ ] `config.py` + `config.example.yaml`: default `file_path` → `logs/event_log.db`
- [ ] `docker-compose.yml`: add `./logs:/app/logs` volume
- [ ] Tests: update `test_event_log.py`, `test_integration_event_pipeline.py`, `test_web_ui_new_endpoints.py`, `test_new_services_extra.py` to the SQLite backend
- [ ] `README.md` + `CHANGELOG.md [Unreleased]`
- [ ] `python -m py_compile` syntax check (work laptop only)
- [ ] **Mac/CI**: `make test` + `make lint` (not run on Windows work laptop)
- [ ] Open PR, verify green, merge

Decisions:
- SQLite chosen over Postgres/MySQL (no extra container/ops; Simplicity First) and
  over a plain JSON-in-volume file (would fix persistence but not the per-event
  full-file rewrite slowness).
- Single connection per instance, `check_same_thread=False` + existing Lock, WAL
  for file DBs, `:memory:` when `persist_to_file=False`.
- Back-compat `entries` property + `store_entry()` keep most existing tests intact.
