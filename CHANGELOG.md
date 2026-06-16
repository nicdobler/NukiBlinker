# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **#141 — Nuki Web API token field in the web UI**: the **Nuki** tab now has an optional **Web API Token** input (password field) so the cloud token that resolves real user names/triggers for Ring-to-Open events can be entered from the UI. Previously this secret could only be set by hand-editing `secrets.yaml`. It is wired through the existing secret-preserving config path: stored in `secrets.yaml`, masked as `***` on `GET /api/config`, and never overwritten by a masked/empty `PUT` (same contract as the Nuki Bridge / Hue / GitHub credentials). The backend support (`nuki.web_api_token` config, `NukiWebClient` instantiation) was already present; this exposes it. Added regression tests for masking, preservation, and update.
- **Real parallel orchestration launcher**: new `script/orchestrate-parallel.ps1` (and `.sh` for Linux/WSL2) spins up **one Windsurf window per issue** for genuine wall-clock parallelism (a single Cascade window only runs issues sequentially). For each issue it classifies feat/fix, creates a worktree + branch from `origin/main`, and drops a `.orchestrate-task.md` brief; in each new window the user types **`/orchestrate-run`** and that agent executes its brief autonomously (implement → test → push → PR → CI green). With `-Wait`/`--wait` the launcher polls GitHub until every PR is green; with `-Merge`/`--merge` it squash-merges in issue order, rebasing the rest. New `/orchestrate-run` workflow; `.orchestrate-task.md` is git-ignored; `/orchestrate` workflow, `Agents.md` and `README.md` document the sequential-vs-parallel choice.
- **#117 — "Send support bundle to GitHub issue"**: a new card on the **Event Log** tab collects the application log slice + event-log entries for a selectable time window (a reference point ± N minutes, default 15) into a **ZIP** (`app-log.txt`, `events.json`, `events.csv`, `metadata.txt`) and opens a GitHub issue with it. Because GitHub's REST API can't attach a binary to an issue, the ZIP is committed (base64) to `support-bundles/<timestamp>.zip` via the Contents API and linked from the issue body. Auth uses `github.token` (or the `GITHUB_TOKEN` env) with `contents:write` + `issues:write`; the repo comes from `github.repo`. The config summary in the issue body is **redacted** (all secret fields masked). New module `nukiblinker/support_bundle.py` (stdlib `zipfile`, existing `httpx`), endpoint `POST /api/support/github-issue`, and `EventLog.get_events_in_range()`. Timezone-aware: the app log (local naive timestamps) and the event log (UTC) are each sliced correctly.
- **#124 — General/Settings web UI tab**: a new **General** tab groups application-wide settings. It exposes **Application Logging** (`logging.file_path`, `logging.rotation_when`, `logging.backup_count`) and a new **GitHub Integration** section (`github.repo`, `github.token`, `github.default_window_minutes`). A new `GithubConfig` model backs it; `github.token` is treated as a **secret** (persisted to `secrets.yaml`, masked as `***` on GET, never overwritten by a masked/empty PUT — same contract as the Nuki/Hue credentials). The section is saved through the existing secret-preserving `PUT /api/config` path. This unblocks the support-bundle feature (#117), which needs `github.token`/`github.repo`. Example files (`config.example.yaml`, `secrets.example.yaml`) updated.
- **`/orchestrate` workflow (multi-issue driver)**: a one-command Windsurf workflow that takes a list of GitHub issue numbers, reads each issue, decides which are parallel-safe (disjoint file sets) vs sequential (overlap/dependency), isolates each in its own git worktree+branch, implements them (via `/new-feature` or `/fix-bug`), pushes, runs the autonomous CI loop, and merges in order with rebases — then cleans up and documents. Documented in `Agents.md` (Subagent Strategy + workflow list) and `README.md`.
- **Parallel-agent tooling (git worktrees)**: new `script/worktree.ps1` (and `script/worktree.sh` for Linux/WSL2) with `new`/`list`/`remove` subcommands to manage git worktrees in a sibling `../NukiBlinker-wt/<branch-slug>` folder, so multiple agents can work in parallel on isolated working trees, each on its own branch from `origin/main`. Added the `/worktree` Windsurf workflow and documented the strategy in `Agents.md` (Subagent Strategy) and `README.md` (Development). Agents only edit and push; CI remains the sole test gate.

### Fixed
- **#161 — Enhanced Nuki Web API logging for name resolution debugging**: added detailed debug logging to `nuki_web_client.get_recent_log()` (request URL, response status, entry count, and first 5 entries with smartlockId/name/trigger/source). Improved logging in `event_router.resolve_person()` when the Web API returns entries but no name is found (now logs how many entries were checked and whether a non-sensor entry was found). This makes it easier to diagnose why a Ring-to-Open event didn't resolve a name from the cloud API.
- **#160 — Smart Lock state 7 (unlatching) now triggers door_opened**: previously only state 5 (unlatched) was recognized, causing "door opened" events to be missed when the lock was actively unlatching (state 7). Both states now correctly trigger the notification.
- **#157 — Correct event mapping: sensor skip, RTO fallback dedup, opener diagnostics** (PR #158):
  - `resolve_person` (Web API path) now skips leading door-sensor log entries (`source=2`, no user identity) to find the real opener's name. Previously `entries[0]` could be a nameless sensor entry that pushed Nico/Ele/Irlene's identity out of sight.
  - Preserves the #155 anti-stale fix: stops at the first *non-sensor* entry — if that entry is also nameless the open is genuinely anonymous and no older entry is used.
  - Deduplicator: added `_rto_fallback_key` for RTO pairs when `ringactionTimestamp` is absent from the bridge callback. A `ring` following an accepted `ring_to_open` from the same device is now suppressed within the window even without a shared timestamp. Standalone rings (no prior `ring_to_open`) are never suppressed by this key.
  - Ignored Opener callbacks now log at INFO level with full payload, enabling diagnosis of app-open events (Irlene scenario) in production logs.

### Removed
- **#106**: Removed the Apple HomePod / AirPlay 2 audio integration (`airplay_client.py`, `pyatv` dependency, `speakers.airplay` config field, AirPlay discovery, and the AirPlay card in the web UI). HomePod RTSP `SETUP` timed out unreliably and produced no audio; the masked `'set' object can't be awaited` warning behind it was the already-fixed #101 bug. HomePod owners are still notified via the HomeKit doorbell. Chromecast / Google Nest is now the only speaker audio channel. Existing `speakers.airplay` keys in `config.yaml` are ignored.

### Fixed
- **#155 — Anonymous Ring-to-Open no longer mistaken for a failure, and stale-name risk removed**: a Nuki *Ring-to-Open* has no associated identity, so no real name can ever be resolved from the Nuki Web API for it — the system correctly falls back to `fallback_name` (e.g. `Alguien`). Two improvements: (1) **stale-name fix** — `resolve_person()` now only trusts the **most recent** Web API log entry (`entries[0]`) instead of scanning the last 20 for the first named one, which could have attributed a stale identity (e.g. yesterday's manual open) to a fresh anonymous open. The most-recent trigger is still surfaced for observability (#97). (2) **clarity** — every resolution now carries a `name_source` (`web_api`/`bridge_log`/`fallback`), and `dispatch_with_actions()` records `"Name: anonymous (no identity resolved)"` in the Event Log when the open is anonymous, so it is no longer mistaken for a name-resolution bug. Added regression tests for the stale-name case and the anonymous indicator.

### Changed
- **#144 — Simplified `NightMode.get_next_change_time` + grace consistency**: collapsed the two redundant `if start_time <= end_time / else` blocks (whose branches were identical dead logic) in both the night and day arms into a single block, and made the reported next change **grace-aware** so it agrees with `is_night_time()` (which already expands the window by `grace_minutes`). Night now reports ending at `end_time + grace` and starting at `start_time - grace`, removing the brief cosmetic disagreement where `active` and `next_change` could differ inside the grace window. Behaviour is unchanged for `grace_minutes=0`. Added regression tests for same-day, overnight, and grace-boundary cases.
- **#145 — Consistent `resolve_person` trigger key**: the Nuki Web API named-entry resolution path now routes its return through the same `_result()` helper as the bridge-log path, so the `trigger` key is present **only when known** instead of being emitted as an explicit `trigger: None`. Both resolution paths now produce a consistent context dict (no functional change today since `context.get("trigger")` already handled `None`, but it removes a latent contract trap). Added a regression test for a named Web API entry with no trigger.
- **#126 — Hue lights/groups as a checkbox list**: the Hue tab no longer asks for comma-separated numeric IDs. It fetches the available lights and groups from the bridge (`GET /api/hue/lights` / `/api/hue/groups`) and renders them as **checkboxes** (name + id); ticking them persists the selection into `hue.lights` / `hue.groups` via the normal config save. If the bridge is unreachable, a clear message is shown and the currently-stored IDs are rendered (checked) so they are **preserved on save** rather than lost. Stored IDs no longer present on the bridge are still shown and kept.
- **#125 — Simplified per-event config UI + relocated Event Log settings + clarified validation vs deduplication**: the **Events** tab now only shows what applies — `ring` (unknown visitor) and `door_opened` are **chime-only** (the TTS mode/message inputs were removed, since a bare ring has no visitor name and door-opened only chimes); `ring_to_open` keeps full TTS. The **Event Logging** settings card moved from the Events tab into the **Event Log** tab where it belongs. The confusing "60 s validation vs 120 s deduplication" overlap is now explicit: **Event Validation** (drops *stale* callbacks, `event_validation.max_delay_seconds`) and **Deduplication** (collapses *repeated* callbacks from one interaction, `deduplication.window_seconds`) are separate, clearly-labelled cards. Deduplication is now editable via a new `GET/PUT /api/config/deduplication` endpoint that also updates the live deduplicator immediately.
- **#130 — Unified `scripts/` into `script/`**: there were two near-identical helper folders. The lone `scripts/validate.sh` was moved to `script/validate.sh` (via `git mv`, history preserved) and `scripts/` was removed. Updated the `make validate` target and the in-file usage comments to point at `script/`. No behaviour change.
- **#123 — Secrets moved to a separate `secrets.yaml`**: secret fields (`nuki.api_token`, `nuki.web_api_token`, `hue.api_key`) are no longer stored inline in `config.yaml`. They live in a dedicated, git-ignored `secrets.yaml` next to it. `load_config` overlays secrets onto the config; `save_config` splits secrets out, writing non-secrets to `config.yaml` and secrets to `secrets.yaml` (both read-back verified). This makes config rewrites from the UI safe **by construction** — they can no longer wipe a stored secret (root cause of #116). An empty or masked (`***`) value never overwrites a stored secret. Existing `config.yaml` files with inline secrets keep working and are migrated to `secrets.yaml` on the next save. New `secrets.example.yaml` template; `docker-compose.yml` mounts `./secrets.yaml`. `install.sh` bootstraps it from the example; `update.sh` creates an **empty** `secrets.yaml` on existing installs (so inline secrets in `config.yaml` migrate cleanly instead of being clobbered by example placeholders) — both before `docker compose up` so the bind mount never turns into a directory.
- **#123 — Config hygiene**: obsolete per-event audio fields are dropped from the persisted `config.yaml` — `message`/`fallback_name` are stripped from `ring` and `door_opened` (there is no known visitor name for a bare ring, and `door_opened` only plays a chime). Old configs with these fields load without error and are cleaned on the next save.
- **Hue blink modes reworked**: each event now chooses between `none`, `short`, or `long`. `short` sends the Hue built-in `select` alert (a single breathe cycle, one blink) and `long` sends `lselect` (~15-second cycle) — both let the Hue bridge restore each light's previous on/off/colour state automatically. The previous configurable `custom` pattern (color / flash count / interval) and its unreliable manual save/restore were removed. Existing configs are migrated automatically (`alert`→`long`, `custom`→`long`). Night mode no longer dims blink brightness (the built-in alerts are bridge-controlled); it still disables audio during quiet hours. The Events tab in the web UI now exposes only the `none`/`short`/`long` selector. A future hardcoded blink pattern can be added in code (no config surface); the `HueClient.get_light_state`/`set_light_state` primitives are retained for that purpose.
- **Event log storage migrated to SQLite**: the event log is now persisted in an embedded SQLite database (`logs/event_log.db`, stdlib `sqlite3` — no new dependency or container) instead of a single JSON file. This fixes two problems the user reported: (1) the log loading slowly (the JSON backend rewrote the whole file on every event and re-parsed it all at startup — events are now single `INSERT`s and the viewer reads them with indexed, paginated SQL queries), and (2) the history being lost between application versions (the `logs/` directory is now mounted as a volume in `docker-compose.yml`, so the DB survives `docker compose build`). A legacy `event_log.json` is migrated into the database automatically on first start (and renamed to `event_log.json.migrated`); a configured `.json` `file_path` is transparently mapped to a sibling `.db`. The default `event_log.file_path` is now `logs/event_log.db`. The `EventLog` public API is unchanged (`server.py`/`web_ui.py` untouched).
- CI failure reporting now keeps a single issue per branch (deduplicated via a hidden marker) instead of opening a new issue on every failing commit, and auto-closes that issue when CI goes green again.

### Fixed
- **#143**: `EventValidator` silently disabled stale-event protection for **naive ISO string timestamps**. A string like `2026-06-14T10:00:00` (no `Z`/offset) parsed to a *naive* `datetime`, and subtracting it from the timezone-aware `now` raised `TypeError`, which the broad fail-safe `except` swallowed — returning `valid=True` for events that should have been rejected as too old. `_parse_timestamp_value` now normalizes naive datetimes to UTC (`dt.replace(tzinfo=timezone.utc)`), so stale naive timestamps are correctly rejected. Added regression tests.
- **#121**: A single Ring-to-Open emitted **two** notifications. The Opener fires two callbacks ~10 s apart that classify as different event types — a `ring_to_open` (state 7) and a `ring` (`ringactionState` true) — so the `(nukiId, event_type, discriminator)` dedup key never collapsed them. Since every Opener callback carries the same `ringactionTimestamp` (the ring that triggered the open, Bridge API §4), the `Deduplicator` now also correlates ring-family events on `(nukiId, ringactionTimestamp)` and suppresses the second one within the window — collapsing one RTO into a single notification. Two genuinely distinct rings (different timestamps) are still delivered.
- **#149**: "Send support bundle to GitHub issue" failed with **HTTP 400** on repos whose **default branch is protected by a ruleset requiring pull requests**. The bundle ZIP was committed **directly to the default branch** via the Contents API, which GitHub rejected with **HTTP 409 "Repository rule violations found — Changes must be made through a pull request"**. The bundle is now committed to a dedicated **`support-bundles`** branch (auto-created from the default branch HEAD via `GitHubClient.ensure_branch`), so the direct commit no longer touches the protected branch. A dedicated 409 error message points at the ruleset if the side branch is also covered. **Diagnosability** was also fixed (the bug was originally undebuggable): both 400 paths in `POST /api/support/github-issue` (missing token, `SupportBundleError`) now log a WARNING with the reason, and a new `_github_error_detail()` extracts GitHub's `message`/`errors`/body into the error (with dedicated 404/409 messages) — the actual cause is now visible in both the UI and the server logs. Added regression tests (branch create/commit via `httpx.MockTransport`, 404/409/422 mapping).
- **#129**: The container crash-looped on startup with `IsADirectoryError: Is a directory: '/app/secrets.yaml'`. When a `docker compose up` runs before `secrets.yaml` exists as a file, Docker auto-creates the bind-mount target as an empty **directory**; `config.py` then did `path.read_text()` after only checking `exists()`, raising on the directory. Two-pronged fix: (1) `load_config`/`_read_yaml_dict` now check `is_file()` and treat a directory as "no usable file" — the app starts (web UI reachable) and logs a clear, actionable error instead of crashing; (2) `update.sh` and `deploy/install.sh` detect a `secrets.yaml`/`config.yaml` **directory** artifact, `docker compose down`, remove it, and recreate the file before `up` so the mount is correct. Added regression tests for the directory case.
- **#115**: Real Nuki ring callbacks were all logged as `Invalid: Event too old` while test events worked. The validator read the lock-state `timestamp` field (per the Bridge API, the *"retrieval of this lock state"* — frequently stale) instead of the actual ring time. It now prefers `ringactionTimestamp` for rings (then falls back to `timestamp`/`time`/`created_at`/`eventTime`), so genuine rings validate against when the bell was pressed.
- **#115**: Event Log viewer only showed the first page — clicking "Load More" went blank when the offset passed the last page. Pagination was reworked into explicit **Previous / Next** controls with a "Page X of Y" indicator, which also fixes the blank-page bug.
- **#112**: `make install` ran `poetry lock` in addition to `poetry install`, which rewrote the committed `poetry.lock` (Poetry version drift) and left the working tree dirty — so a later `make cleanup` failed at `git pull --ff-only` ("cannot pull with rebase: You have unstaged changes"). `install` now only runs `poetry install`; lockfile regeneration moved to a dedicated `make lock`. Also added `.homekit/` (and `homekit/`) to `.gitignore` to stop the HomeKit pairing-state directory showing up as an untracked artifact.
- **Code review**: Batch of bug fixes from a full-codebase review:
  - Web UI feature-config endpoints (`/api/config/event-validation|night-mode|event-log`) now persist to the launch `--config` path instead of a hardcoded `./config.yaml`, preventing config drift / lost changes in the Dockerized deploy.
  - `PUT /api/config` no longer wipes stored Nuki/Hue credentials when the request omits the `nuki`/`hue` sections (omitted sections are preserved like masked secrets).
  - Event deduplication no longer collapses two genuinely distinct `ring_to_open`/`door_opened` events: the discriminator now prefers a per-event `timestamp` (falling back to `state` for burst suppression when no timestamp is present).
  - Chromecast name-based playback no longer leaks a `Zeroconf`/`CastBrowser` per event, and cast socket clients are now disconnected after playback; `volume_level == None` is handled when saving/restoring volume.
  - Event-log CSV export now renders a `0.00` ms processing time instead of a blank cell, and the temporary CSV file is deleted after the response is sent.
  - `/api/test/event` now mirrors the real pipeline (applies night mode and records the event in the Event Log). The detailed action list — which may embed exception text — is kept in the Event Log only and is no longer echoed in the HTTP response (CodeQL `py/stack-trace-exposure`).
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
- **#115**: Application logs are now written to a rotating file (`logs/nukiblinker.log`) in addition to the console. A `TimedRotatingFileHandler` rotates **weekly** and keeps a configurable number of old files (`logging.backup_count`, default 4) for basic housekeeping. New `logging` config block (`file_path`, `rotation_when`, `backup_count`); set `file_path` empty to disable file logging.
- **#115**: Event Log CSV export now includes a **`Payload (JSON)`** column with the full raw Nuki payload (previously only visible on screen).
- **#115**: Devices are now identified by **name** instead of `nukiId` across the Event Log viewer, the device filter, and the CSV export. The Nuki Device Filter now persists the selected Opener/Lock names (`nuki.opener_name`, `nuki.lock_name`), which are used to resolve `nukiId` -> name even though real callbacks don't carry a name.
- **Ops**: `update.sh` (project root, executable) — one-command update for the Mini PC: pulls latest code + image, ensures the `logs/` volume dir exists, restarts the container, and prunes dangling images (`BUILD=1` to build locally).
- **Dev**: Mac branch workflow as Make targets — `make run-tests` (lint + tests on the current branch), `make validate` (fetch + pick a branch + checkout + install + run-tests, backed by `scripts/validate.sh`), and `make cleanup` (return to main, pull, prune merged local branches). `make test`/`make lint` keep their original meaning.
- **Repo**: `.gitattributes` enforcing `eol=lf` for `*.sh` so scripts authored on the Windows work laptop keep a working shebang on macOS/Linux.
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
