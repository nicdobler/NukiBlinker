# Tasks

---

## #157 Event mapping corrections ✅ DONE

**Branch**: fix/157-event-mapping | **PR**: #158 | squash-merged to main.

Four bugs fixed in one commit:

1. **Sensor skip in resolve_person (Web API)** — door-sensor entries (`source=2`) were masking the real opener's name. Now skips leading sensor entries to find the first non-sensor entry; stops there (preserving #155 anti-stale protection).
2. **RTO fallback dedup** — when `ringactionTimestamp` is absent from the `ring_to_open` bridge callback, a new `_rto_fallback_key (nukiId, "rto_seen")` suppresses the paired `ring`. Only registered on `ring_to_open`, never on `ring`, so standalone rings (visitor buzzing) pass through.
3. **Opener diagnostic logging** — ignored Opener callbacks now log at INFO with full payload (state, ringactionState, ringactionTimestamp) instead of DEBUG. Enables diagnosis of app-open events (Irlene scenario).
4. **Tests** — 6 new/updated tests in `test_deduplication.py` and `test_event_router.py`.

Open: Paso 5 (NukiWeb webhook for reliable app-open detection from Opener) remains out of scope — requires spec update before implementation.

---

## #149 Support-bundle GitHub-issue 400 — TWO PRs ✅ DONE

**PRs**: #151 (diagnosability), #153 (real root-cause fix) | both squash-merged | Issue closed.

Round 1 (#151): bare 400 with no server-side reason. Fixed diagnosability — log
WARNING on both 400 paths; new `_github_error_detail()` surfaces GitHub
`message`/`errors`/body; dedicated 404 message. This made the real cause visible.

Round 2 (#153): user reopened with the log the fix surfaced —
`HTTP 409 Repository rule violations found · Changes must be made through a pull
request`. **Real root cause**: the bundle ZIP was committed **directly to the
default branch** (Contents API), which the repo's branch ruleset blocks. Fix:
commit to a dedicated **`support-bundles`** branch via new
`GitHubClient.ensure_branch()` (auto-created from default HEAD); `commit_file`
takes a `branch` param; dedicated 409 message; injectable httpx transport for
tests (`httpx.MockTransport`). Workflow: `/orchestrate #149`, sequential
worktree, Auto wrap-up. Lesson: surfacing the real error first (round 1) was
what made the genuine fix (round 2) possible.

---

## Code-review follow-ups (#143, #144, #145) — parallel orchestration ✅ DONE

**PRs**: #146 (#143), #147 (#144), #148 (#145) — all squash-merged to `main`, issues closed.
Note: launcher merged #146 then its single merge-pass skipped #147/#148 (rebase
restarted their CI → seen as PENDING). Finished manually: merged #147, rebased
#148 (CHANGELOG conflict resolved — kept both entries), CI green, merged #148.

Source: `/review` of event pipeline (event_router, deduplication, event_validator,
night_mode, notifier). Wrap-up mode: **Auto**. Execution: **real parallel** via
`script/orchestrate-parallel.ps1 -Issues 143,144,145 -Wait -Merge` (one Windsurf
window per issue; paste `/orchestrate-run` in each).

- **#143** (bug, `fix/`): `event_validator` naive ISO timestamps → naive datetime
  vs aware `now` raises `TypeError`, swallowed by fail-safe → validation silently
  skipped. Fix: normalize naive → UTC. Add regression test.
- **#144** (refactor, `feat/`): `night_mode.get_next_change_time` redundant
  identical if/else branches + grace-period inconsistency with `is_night_time`.
- **#145** (refactor, `feat/`): `resolve_person` Web-API path emits explicit
  `trigger: None`; route through `_result()` so the key is omitted when unknown.

Batching: disjoint file sets (event_validator.py / night_mode.py / event_router.py)
→ parallel-safe, merge in any order.

---

## #123 Config hygiene + secret persistence — separate `secrets.yaml`

**Branch**: `fix/123-secrets-separate-file` | **PR**: _pending_

Context: #123 (split from #116 token loss + #118 config hygiene). Decision this
session: store secrets in a **separate `secrets.yaml`** (user chose "separar
secrets ahora"). Wrap-up mode: **Auto**. Secret transport: **file only** (no env
var override).

Design: secrets (`nuki.api_token`, `nuki.web_api_token`, `hue.api_key`) live in
`secrets.yaml` next to `config.yaml`, never inline. `load_config` overlays
secrets onto config; `save_config` splits secrets out, strips obsolete fields,
writes both files with read-back verification. Secret preservation: empty/`***`
never overwrites a stored secret. Old inline-secret configs migrate on next save.
`AppConfig` keeps secret fields in memory → rest of app unchanged.

- [x] Specs updated (product-spec Secret storage + hygiene; tech-spec config.py + volumes)
- [x] config.py: SECRET_FIELDS, load overlay, save split + preserve + normalize
- [x] web_ui.py: verified — GET mask / PUT preserve still consistent (defense in depth, no change)
- [x] .gitignore (secrets.yaml), docker-compose volume, config.example cleanup, secrets.example.yaml, install.sh bootstrap
- [x] Tests: migration, save preserves secrets, secrets absent from config.yaml, obsolete fields stripped
- [x] README + CHANGELOG + deploy/README
- [ ] CI green → auto wrap-up

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

**Branch**: `feat/event-log-sqlite` | **PR**: #111

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

---

## #112 — `make cleanup` failed: dirty poetry.lock from `make install`

**Branch**: `fix/112-poetry-lock-churn` | **PR**: #113

Context: `make cleanup` aborted at `git pull --ff-only` with "cannot pull with
rebase: You have unstaged changes". Root cause: `make install` ran `poetry lock`
on top of `poetry install`, rewriting the committed `poetry.lock` (Poetry version
drift) and dirtying the tree; `make validate` runs `make install`, so the dirty
lock surfaced on the next `make cleanup`.

- [x] Root cause identified (Makefile `install` runs `poetry lock`)
- [x] Fix: `install` only runs `poetry install`; move `poetry lock` to a dedicated `make lock`
- [x] `.gitignore`: ignore `.homekit/` and `homekit/` (runtime artifact in the trace)
- [x] Regression test `tests/test_makefile.py` (fails on pre-fix Makefile)
- [x] Docs: CHANGELOG `[Unreleased]` + `tasks/lessons.md`
- [ ] **Mac/CI**: `make test` + `make lint` (not run on Windows work laptop)
- [ ] Merge PR #113

---

## Event log fixes + app log to file (#115)

**Branch**: `fix/event-log-and-app-logging` | **PR**: #119

Context: User parked `feat/hue-blink-select-lselect` to troubleshoot the event log
and app logging. Real Nuki callbacks were all logged as `Invalid` while test events
worked; the event-log viewer only showed page 1 ("Load More" went blank); CSV export
lacked the payload; devices were shown by ID; and there was no app log file. The
"send logs to a GitHub issue" button was split out to issue #117 (separate session).

Phases (each with tests):
- [x] Phase 0: specs (product + tech) + CHANGELOG
- [x] Phase 1: validator prefers `ringactionTimestamp` (real rings no longer Invalid) + regression test
- [x] Phase 2: store `opener_name`/`lock_name` in Nuki Device Filter config; resolve `nukiId`->name in viewer/filter/CSV
- [x] Phase 3: Prev/Next pagination + page indicator; add `Payload (JSON)` CSV column; verify export scope
- [x] Phase 4: app log to file with weekly `TimedRotatingFileHandler` + `LoggingConfig`
- [x] **Mac/CI**: `make test` + `make lint`
- [x] Push branch + open PR (#119)

Decisions:
- Root cause of "all real events Invalid": validator read the lock-state `timestamp`
  ("retrieval of this lock state", often stale) instead of the actual ring time
  (`ringactionTimestamp`). Test events send `{}` -> no timestamp -> valid.
- Device naming reuses the existing Device Filter config (`opener_id`/`lock_id`)
  by also persisting their names, rather than depending on a live bridge call at view time.
- GitHub support-bundle button deferred to #117 (PAT + ZIP via Contents API, time window).

---

## Hue blink modes: none / short (select) / long (lselect)

**Branch**: `feat/hue-blink-select-lselect` | **PR**: #114

Context: User asked whether the built-in Hue alerts can have fewer blinks. The
built-in `lselect` (~15s) is fixed; only `select` (single cycle) reduces it.
Decision (user): per-event choice between a 1-cycle and a 15-second blink,
remove the broken `custom` mode, leave room for a future hardcoded pattern (no
config), and guarantee lights return to their previous state — which the
built-in `select`/`lselect` already do via the bridge.

Note: rebased on top of `main` after #119 (event-log fixes) merged; the two
PRs overlapped only in shared docs/config files (auto-merged) and this
`tasks/todo.md` append (resolved by keeping both entries).

- [x] Specs: product-spec Blink Modes (none/short/long) + tech-spec config model, HueClient, night mode
- [x] `config.py`: `BlinkConfig` modes none/short/long; removed `CustomBlinkConfig`; `field_validator` migrates `alert`/`custom`→`long`; new defaults (ring=long, ring_to_open=short)
- [x] `hue_client.py`: `trigger_alert(..., alert="lselect")`; removed `trigger_custom_blink`; kept `get_light_state`/`set_light_state` for a future pattern
- [x] `notifier.py`: `_BLINK_ALERT` mode→alert map + documented extension hook
- [x] `night_mode.py`: dropped custom-brightness branch (built-in alerts are bridge-controlled)
- [x] Web UI: Events tab selector none/short/long; removed custom inputs + `toggleCustomBlink` JS
- [x] Tests: hue_client (alert kind), notifier, night_mode, config (migration), integration pipeline
- [x] Docs: README, config.example.yaml, CHANGELOG `[Unreleased]`
- [ ] **CI**: lint + test (sole validation env)
- [ ] Merge PR

---

## Parallel-agent tooling — git worktrees

**Branch**: `chore/worktree-tooling` | **PR**: _pending_

Context: User wants to launch independent agents in parallel on this repo
without working-tree conflicts. Chose git worktrees (one folder + branch per
agent, created from `origin/main`). Mode: **edit + push only** — no `.venv`, no
local tests; CI stays the sole validation gate. Initial mount executed so a
later session can just request "launch N subagents".

- [x] `script/worktree.ps1` (new/list/remove) matching repo script style
- [x] `script/worktree.sh` parity for Linux/WSL2
- [x] `.windsurf/workflows/worktree.md` workflow (create/launch/push/merge/cleanup)
- [x] `Agents.md`: Subagent Strategy → parallel-agents-via-worktrees + workflow list
- [x] `README.md` Development: "Parallel agents (git worktrees)" section
- [x] `CHANGELOG.md` `[Unreleased]` → Added
- [x] Initial mount: created `../NukiBlinker-wt/` root + validated script
- [x] **CI**: green (PR #131)
- [x] Merge PR #131 (squash) + cleanup

---

## `/orchestrate` — one-command multi-issue driver

**Branch**: `chore/orchestrate-workflow` | **PR**: _pending_

Context: User wants a fully automatic flow — "trabaja las issues X Y Z" — where
the orchestrator (this Cascade window on `main`) decides parallel vs sequential,
isolates each issue in a worktree, implements, pushes, watches CI, and merges in
order. Honest limit stated: one Cascade runs issues sequentially but isolated per
branch; wall-clock concurrency needs one window per worktree.

- [x] `.windsurf/workflows/orchestrate.md` (gather → batch → worktree → implement → push → CI loop → merge → cleanup)
- [x] `Agents.md`: Subagent Strategy → multi-issue orchestration + workflow list
- [x] `README.md` Development: orchestrate note
- [x] `CHANGELOG.md` `[Unreleased]` → Added
- [ ] **CI**: lint + test (sole validation env)
- [ ] Merge PR

---

## `/orchestrate 129 130 126 125 124 117 121` — batch of 7 issues

**Wrap-up mode**: Approval per PR (user decides each merge). Each issue isolated in
its own worktree+branch from `origin/main`. CI is the sole gate.

**Batching decision**:
- Parallel-safe (disjoint files): #121 (event_router/dedup), #130 (scripts folder), #129 (config.py + deploy).
- Sequential UI chain (share `static/index.html` + `web_ui.py` + `config.py`): #124 → #125 → #126 → #117. #124 first (adds `GithubConfig`, unblocks #117); #117 last.

**Status (all pushed, CI GREEN, awaiting approval)**:
- [x] #121 `fix/121-rto-double-notify` | **PR #133** | CI green — RTO ring+ring_to_open collapsed via `(nukiId, ringactionTimestamp)` correlation.
- [x] #130 `chore/130-unify-scripts` | **PR #134** | CI green — `scripts/validate.sh` → `script/`, removed `scripts/`.
- [x] #129 `fix/129-secrets-isadirectory` | **PR #135** | CI green — `is_file()` guard + deploy directory-artifact repair.
- [x] #124 `feat/124-general-settings-tab` | **PR #136** | CI green — General tab (logging + GitHub config), `GithubConfig` secret.

**UI chain (sequential, each branched from updated `main` after the previous merge)**:
- [x] #125 `feat/125-simplify-event-config` | **PR #137** | merged — chime-only ring/door, Event Log settings relocated, validation vs dedup split + `/api/config/deduplication`.
- [x] #126 `feat/126-hue-checkbox-list` | **PR #138** | merged — lights/groups as checkboxes from the bridge, fallback preserves stored IDs.
- [x] #117 `feat/117-support-bundle` | **PR #139** | merged — `support_bundle.py`, `POST /api/support/github-issue`, Event Log tab UI, `EventLog.get_events_in_range`.

**Outcome (mode switched to Auto wrap-up mid-session)**: all 7 PRs (#133–#139)
went green and were squash-merged into `main` in dependency order. The only
rebase needed was #135 (CHANGELOG `### Fixed` conflict with #133) — resolved by
keeping both entries. Worktrees + merged local branches cleaned up. `main` is at
`d38487b`. Note: this `tasks/todo.md` log is an uncommitted working-tree change
on `main` (Rule 10 — never commit to `main` directly).

---

## #141 Nuki web integration — Web API token field in the UI

**Branch**: `feat/141-nuki-web-api-token-ui` | **PR**: _pending_

Context: issue #141 — no UI field to enter the Nuki **Web API** token used to
resolve the RTO user name. Backend already supported `nuki.web_api_token`
(config field, secret masking/preservation in `web_ui.py`, `NukiWebClient`
instantiation in `__main__.py`); only the web UI input was missing. Wrap-up
mode: **Auto**.

- [x] Spec gate: product-spec Nuki tab section documents the masked Web API token field.
- [x] `index.html`: add `nukiWebToken` password input + load (`loadBaseConfig`) + save (`saveBaseConfig`) wiring.
- [x] `test_web_ui.py`: fixture sets `web_api_token`; tests for GET masking, omitted-section preservation, masked `***` no-overwrite, and new-value save.
- [x] Docs: README (Nuki tab row + setup step 6), CHANGELOG `[Unreleased] / Added`.
- [ ] Push branch → CI green → auto wrap-up (squash-merge).

---

## #155 — Anonymous Ring-to-Open clarity + Web API stale-name fix

**Branch**: `fix/155-anonymous-and-stale-name` | **PR**: _pending_

Context: support-bundle issue #155 reported a Ring-to-Open at ~12:22 where "no
name was retrieved from Nuki Web". Investigation: a Nuki RTO is **anonymous**
(no associated identity), so the fallback name is the *expected* outcome, not a
failure. The bundle window (11:01-11:31 UTC) didn't even cover the event
(10:22 UTC), explaining the 0 event-log entries. No confirmed defect; user
chose two improvements. Wrap-up mode: **Auto**.

- [x] Spec gate: tech-spec Nuki Web API section documents most-recent-only resolution + `name_source` provenance.
- [x] `event_router.resolve_person`: only trust most-recent Web API entry (stale-name fix #155); add `name_source` (`web_api`/`bridge_log`/`fallback`).
- [x] `event_router.dispatch_with_actions`: surface `"Name: anonymous (no identity resolved)"` when `name_source == fallback`.
- [x] Tests: updated 13 resolve_person assertions for `name_source`; added stale-name regression + anonymous-indicator tests.
- [x] Docs: CHANGELOG `[Unreleased] / Fixed`, tech-spec.
- [ ] Push branch → CI green → auto wrap-up (squash-merge).
