# NukiBlinker

Reacts to Nuki doorbell and Smart Lock events with configurable notifications: Hue light blinks, voice announcements on Google Nest, and Apple HomeKit doorbell push notifications.

## Documentation

All project documentation lives in this repository (versioned alongside the code):

| Document | Purpose |
|---|---|
| [`specs/product-spec.md`](specs/product-spec.md) | What & why — vision, event types, channels, acceptance criteria, non-goals |
| [`specs/tech-spec.md`](specs/tech-spec.md) | How — architecture diagrams, component/class design, data model, APIs, CI |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history (Keep a Changelog + SemVer) |
| [`config.example.yaml`](config.example.yaml) | Annotated configuration template (non-secrets) |
| [`secrets.example.yaml`](secrets.example.yaml) | Secrets template (`secrets.yaml`) |
| [`deploy/README.md`](deploy/README.md) | Bare-metal / systemd deployment notes |

## Features

- **3 event types**: Ring (unknown visitor), Ring to Open (authorized), Door Opened (Smart Lock)
- **Per-event rules**: each event gets its own blink pattern, audio, and HomeKit toggle
- **Personalized announcements**: "{name} llegó a casa" — the visitor name is resolved **only** from the Nuki Web API activity log (a Web API token is required; without it announcements use the fallback name)
- **Hue light blinks**: built-in alert per event — `short` (1 blink) or `long` (~15s); lights restore their previous state automatically
- **Voice announcements**: TTS via gTTS on Google Nest (Chromecast), cached on a persistent volume so repeated messages replay instantly
- **Chime sound**: a single built-in doorbell chime for ring / door-opened events (fixed, not configurable)
- **Apple HomeKit**: virtual doorbell accessory — notifications on all paired Apple devices, plus a programmable button usable as a Home app automation trigger
- **Event validation**: configurable timestamp validation to reject stale events
- **Event deduplication**: collapses the burst of callbacks one real interaction emits (a genuine second ring still notifies)
- **Event logging**: comprehensive event history with detailed action tracking, device filtering by **name + type + ID**, an **only-events-with-actions** filter, per-entry device-type badge, Previous/Next pagination, and Excel-friendly CSV export (local timezone, separate Date/Time columns, full payload JSON)
- **Application log to file**: rotating app log (`logs/nukiblinker.log`) with basic weekly housekeeping, alongside console output
- **Optional Nuki Web API**: resolve real user names and action triggers from the cloud activity log (read-only)
- **Night mode**: time-based notification adjustments (disables audio during quiet hours)
- **Web UI**: comprehensive tabbed config UI at `http://localhost:8080/` — device discovery, guided pairing, full event rules, event log viewer
- **Auto-discovery**: Nuki Bridge, Hue Bridge, and Chromecast speakers
- **Graceful lifecycle**: shutdown deregisters Nuki callback, pause/resume via web UI

## Prerequisites

- **Nuki Opener** and/or **Smart Lock** connected to a **Nuki Bridge**
- **Philips Hue Bridge** on the same LAN
- **Docker** (recommended), or **Python >= 3.11** + [Poetry](https://python-poetry.org/)
- Optional: Google Nest / Chromecast speakers

> **Note**: Apple HomePod / AirPlay audio output was removed in v0.4.x (HomePod RTSP setup timed out unreliably). HomePod owners still get the ring via the HomeKit doorbell notification.

## Quick Start

```sh
cp config.example.yaml config.yaml
cp secrets.example.yaml secrets.yaml
docker compose up -d
```

Open `http://localhost:8080/` on the Mini PC to configure via the web UI.

> Secrets (Nuki/Hue tokens) live in `secrets.yaml`, **not** `config.yaml` (#123), so saving config from the UI can never wipe them. You can leave `secrets.yaml` empty and fill the tokens in via the web UI.

## Initial Setup Guide

After starting the container, open the web UI and follow these steps in order:

### 1. Connect the Nuki Bridge

Go to the **Nuki** tab.

1. Click **Discover** to find your Nuki Bridge on the LAN, or enter the IP manually.
2. Enter the **API Token** (find it in the Nuki app → Settings → Manage Bridge → Enable API).
3. Click **Save** in the bottom bar.
4. Click **Register Callback** — this tells the Bridge to send events (ring, door open) to NukiBlinker.
5. Optionally, click **List Devices** and click on a device to filter events to a specific Opener or Smart Lock.
6. Optionally, enter a **Web API Token** (read-only cloud token from [web.nuki.io](https://web.nuki.io) → API → Web API Tokens) to resolve the real user name/trigger for Ring-to-Open announcements. It is stored as a secret in `secrets.yaml`.

### 2. Connect the Hue Bridge

Go to the **Hue** tab.

1. Click **Discover** to find the Hue Bridge IP, or enter it manually.
2. **Press the physical button** on top of the Hue Bridge.
3. Click **Pair** within 30 seconds — the API key is generated and saved automatically.
4. Click **List Lights** and/or **List Groups** — click on the ones you want to blink on events.
5. Click **Save**.

### 3. Add speakers (optional)

Go to the **Speakers** tab.

1. Click **Discover** under Chromecast to find speakers on the network.
2. Click on a speaker to add it, or type names manually (one per line).
3. Adjust the **Volume** slider.
4. Click **Save**.

### 4. Enable HomeKit (optional)

Go to the **HomeKit** tab.

1. Toggle **Enabled** on.
2. Note the **Setup Code** — use it to add the virtual doorbell in the Apple Home app.
3. Click **Save**.

### 5. Configure event rules

Go to the **Events** tab. Each event type (Ring, Ring to Open, Door Opened) has its own settings:

- **Blink mode**: `none`, `short` (single Hue built-in blink), or `long` (~15s Hue built-in). Lights return to their previous state automatically.
- **Audio**: enable TTS announcements (with `{name}` placeholder) or play a chime sound.
- **HomeKit**: toggle doorbell notification per event.

Click **Save** when done.

### 6. Test it

Go to the **Status** tab and click **Test** next to any event type to trigger it. Check that your lights blink, speakers play, and HomeKit sends a notification.

## Web UI

The web UI provides a tabbed interface covering all configuration:

| Tab | Features |
|---|---|
| **Status** | Pause/resume, test events, server host/port |
| **Nuki** | Bridge connection, network discovery, callback registration, device filter (opener/lock ID), optional Web API token |
| **Hue** | Bridge connection, network discovery, guided pairing (button press → pair), light & group selection |
| **Speakers** | Chromecast names, network discovery, volume slider |
| **HomeKit** | Enable/disable, setup code, persist directory |
| **Events** | Per-event blink (none/short/long), audio (TTS/chime), HomeKit toggle |
| **Event Log** | View event history, filter by device (name + type + ID) or only events with actions, export CSV, clear log |
| **Event Validation** | Configure timestamp validation to reject stale events |
| **Night Mode** | Set quiet hours with reduced notifications |

Mandatory fields are marked with a red `*`. Changes are saved to `config.yaml` via the fixed save bar.

### New Features

#### Event Validation
Prevents stale events from triggering notifications by checking event timestamps:
- Configurable maximum delay (default: 60 seconds)
- Handles missing or future timestamps gracefully
- Rejects events older than the threshold with detailed logging

#### Event Logging
Comprehensive event history for monitoring and troubleshooting:
- Embedded **SQLite** storage (`logs/event_log.db`) with configurable retention — fast to load and **persists across application/container updates** (when `./logs` is mounted as a volume)
- Detailed action tracking with processing times
- Each entry is timestamped with the **real event time** (#204), not the callback receive time: a ring uses the Bridge `ringactionTimestamp`, a ring-to-open uses the matched Nuki Web entry date, everything else uses the receive time. Stored in UTC, shown in local time.
- CSV export for analysis (includes a `Payload (JSON)` column with the full raw payload)
- Web UI viewer with Previous/Next pagination, device filtering by **name + type (Opener / Smart Lock) + ID**, an **only-events-with-actions** checkbox, and a per-entry device-type badge (the Nuki Device Filter remembers the Opener/Lock names; real callbacks carry no name)
- Expandable detail panel shows the **raw Nuki Web API response** (`nuki_web_response`) for Opener `ring`/`ring_to_open` events when the Web API is configured; otherwise it shows "none" (#232)
- A legacy `event_log.json` is migrated into the database automatically on first start

#### Night Mode
Reduces notifications during specified hours:
- Configurable time windows (default: 22:00-07:00)
- Grace periods for smooth transitions
- Audio suppression during night hours
- Reduced light brightness (configurable factor)
- HomeKit notifications preserved for security

## Configuration

See `config.example.yaml` (non-secrets) and `secrets.example.yaml` (secrets) for all options.

**Secrets** (`nuki.api_token`, `nuki.web_api_token`, `hue.api_key`) are stored in `secrets.yaml`, never inline in `config.yaml` (#123). The web UI writes them there; an old `config.yaml` with inline secrets is migrated automatically on the next save.

Key `config.yaml` sections:

- **nuki** — Bridge IP, port, optional opener/lock ID filters
- **hue** — Bridge IP, light/group IDs
- **speakers** — Chromecast speaker names, volume
- **homekit** — Enable/disable, setup code
- **events** — Per-event rules (ring, ring_to_open, door_opened)
- **event_validation** — Timestamp validation settings
- **night_mode** — Quiet hours and notification adjustments
- **event_log** — Logging configuration, retention, and CSV timezone
- **deduplication** — Suppress duplicate events from one interaction (enabled, window_seconds)
- **logging** — Application log file: path, weekly rotation, and number of files kept
- **server** — Host and port

### New Configuration Options

#### Event Validation
```yaml
event_validation:
  enabled: true
  max_delay_seconds: 60  # Reject events older than 60 seconds
```

#### Night Mode
```yaml
night_mode:
  enabled: true
  start_time: "22:00"
  end_time: "07:00"
  brightness_factor: 0.3  # Reduce light brightness to 30%
  grace_minutes: 5        # Grace period around boundaries
```

#### Event Logging
```yaml
event_log:
  enabled: true
  max_entries: 1000       # Maximum events kept in the database
  retention_days: 7       # How long to keep events
  persist_to_file: true   # Persist to the SQLite DB (false = in-memory only)
  file_path: "logs/event_log.db"  # SQLite DB on the ./logs volume (legacy .json auto-migrated)
  timezone: "Europe/Madrid"  # IANA tz for the CSV Date/Time columns
```

#### Application Log File
```yaml
logging:
  file_path: "logs/nukiblinker.log"  # on the ./logs volume; empty disables file logging
  rotation_when: "W0"     # weekly (Monday); TimedRotatingFileHandler `when`
  backup_count: 4         # number of rotated files kept
```

#### Event Deduplication
```yaml
deduplication:
  enabled: true
  window_seconds: 120     # suppress duplicate events within this window
```

#### Opener open correlation (#180)
```yaml
opener_correlation:
  enabled: true              # correlate ignored opener callbacks with Nuki Web
  window_seconds: 10         # how long to keep polling Nuki Web
  poll_interval_seconds: 2.0 # delay between polls
  recency_seconds: 60        # max age of a Web entry to count as "this open"
```
Some user opens (e.g. opening from the Nuki app while Ring-to-Open is active) never produce a `ring_to_open` callback — only routine opener status callbacks arrive. When enabled (and a Nuki Web token is configured), NukiBlinker polls the Nuki Web log after such a callback and fires the **ring to open** rule if a user-attributed open appears in the window.

#### Nuki Web API (name/trigger resolution)
Stored in `secrets.yaml` (it is a secret), not `config.yaml`:
```yaml
# secrets.yaml
nuki:
  web_api_token: ""       # cloud token; resolves real names + how the door was opened
```
Name resolution for **Opener** events (ring / ring to open) is done **exclusively** via the Nuki Web API — the local Bridge `/log` is no longer used. Without a token, announcements use the fallback name. **Door opened** (Smart Lock) events never resolve a name (chime/blink only).

> **Device ID mapping (#190)**: the Nuki Bridge `nukiId` and the Nuki Web API `smartlockId` are **different** identifiers. For efficient per-device log queries, set `nuki.opener_web_id` / `nuki.lock_web_id` in `config.yaml` to the Web API `smartlockId` for each device. Use the **Nuki Web Devices** button in the Nuki tab (or `GET /api/nuki/web-devices`) to look up the correct IDs. Without these fields, the global log endpoint is used (works but less efficient for multi-device accounts).

### Getting API Keys

- **Nuki Bridge**: Nuki app → Settings → Manage Bridge → Enable API. Note the token. Or use the Web UI's Nuki tab.
- **Hue Bridge**: Use the Web UI's Hue tab (Discover → press bridge button → Pair), or manually: `POST http://<bridge-ip>/api {"devicetype":"nukiblinker"}`.

### API Endpoints (Web UI)

| Endpoint | Method | Description |
|---|---|---|
| `/api/config` | GET/PUT | Read/write full configuration |
| `/api/discover/nuki` | GET | Discover Nuki Bridges on LAN |
| `/api/discover/hue` | GET | Discover Hue Bridges on LAN |
| `/api/discover/speakers` | GET | Discover Chromecast speakers |
| `/api/nuki/pair` | POST | Register callback on Nuki Bridge |
| `/api/nuki/devices` | GET | List Nuki devices |
| `/api/nuki/callbacks` | GET | List registered callbacks |
| `/api/hue/status` | GET | Check Hue Bridge connection & API key validity |
| `/api/hue/pair` | POST | Pair with Hue Bridge (tries existing key first) |
| `/api/hue/lights` | GET | List Hue lights |
| `/api/hue/groups` | GET | List Hue groups |
| `/api/homekit/qr` | GET | HomeKit setup code, pairing status & QR (SVG) |
| `/api/status` | GET | Service status |
| `/api/pause` | POST | Pause service |
| `/api/resume` | POST | Resume service |
| `/api/test/event/{type}` | POST | Fire test event |
| `/api/events/log` | GET | Get paginated event log (`?device_id=` and/or `?actions_only=1` to filter); each event includes `nuki_web_response` when a Web API call was made |
| `/api/events/devices` | GET | List distinct devices seen in the event log |
| `/api/events/export` | GET | Export event log as CSV (`?device_id=` to filter) |
| `/api/events/clear` | POST | Clear all event log entries |
| `/api/config/event-validation` | GET/PUT | Event validation configuration |
| `/api/config/night-mode` | GET/PUT | Night mode configuration |
| `/api/config/event-log` | GET/PUT | Event logging configuration |

## Deployment (Mini PC)

### First-time setup

```sh
mkdir -p nukiblinker && cd nukiblinker
# Copy docker-compose.yml, config.example.yaml and secrets.example.yaml from the repo
cp config.example.yaml config.yaml
cp secrets.example.yaml secrets.yaml
```

The `docker-compose.yml` mounts `./logs:/app/logs` so the event-log SQLite
database (`logs/event_log.db`) survives `docker compose build` rebuilds. Without
this volume the event history is wiped on every redeploy.

It also mounts `./cache:/app/cache` for the **persistent TTS cache** (#178):
generated announcement `.mp3` files are stored under `cache/tts` (keyed by the
spoken message) and reused across restarts so repeated messages replay
instantly. The directory is overridable with the `NUKIBLINKER_TTS_CACHE_DIR`
environment variable (default `cache/tts`).

Edit `config.yaml` with your Nuki/Hue Bridge IPs and `secrets.yaml` with your tokens/keys (or configure everything later via the web UI).

### Start / update

```sh
docker compose build && docker compose up -d
```

Or use the one-command helper from the project directory:

```sh
./update.sh
```

It pulls the latest code + image, ensures the `logs/` volume dir exists, restarts
the container, and prunes dangling images. Pass `BUILD=1 ./update.sh` to build the
image locally instead of pulling it.

### View logs

```sh
docker compose logs -f --tail 50
```

### Stop

```sh
docker compose down
```

### Access the web UI

Open `http://localhost:8080/` from a browser on the same machine, or `http://<mini-pc-ip>:8080/` from another device on the LAN.

The admin API (`/api/*`) and web UI (`/`) are restricted to **private-network IPs** (localhost, Docker gateway, LAN). Requests from public IPs are blocked with 403. The `/health` and `/nuki/callback` endpoints are accessible from any IP.

## Troubleshooting

### 403 Forbidden when accessing the web UI

The admin middleware blocks requests from non-private IPs. Common causes:

- **Accessing via a public IP or reverse proxy** that doesn't forward the real client IP. Access via `localhost` or a LAN IP (192.168.x.x, 10.x.x.x) instead.
- **VPN or unusual network setup** where the client IP appears non-private.

### ConnectTimeout when registering Nuki callback

The container cannot reach the Nuki Bridge. Check:

- **Nuki Bridge is powered on** and connected to your WiFi.
- **Bridge IP is correct** in `config.yaml` (use the Nuki app → Bridge settings to verify).
- **Docker networking**: the container uses `network_mode: host`, so it shares the host's network stack. If running on WSL2, make sure the WSL2 VM can reach the LAN (see WSL2 section below).

The app starts normally even if callback registration fails — you can re-register later from the web UI (Nuki tab → Register Callback).

### Container starts but callback URL is wrong

When `server.host` is `0.0.0.0`, NukiBlinker auto-detects the LAN IP for the callback URL sent to the Nuki Bridge. If auto-detection picks the wrong IP (e.g., Docker internal IP), set `server.host` to your actual LAN IP:

```yaml
server:
  host: "192.168.1.50"   # Your Mini PC's LAN IP
  port: 8080
```

> **Note**: This also changes the bind address. Use `0.0.0.0` to bind on all interfaces (recommended) and let auto-detection handle the callback URL.

### Getting the Nuki Bridge API token

1. Open the **Nuki app** on your phone.
2. Go to **Settings → Manage my devices → Nuki Bridge**.
3. Enable **HTTP API** if not already enabled.
4. The app shows the **API token** — copy it into `secrets.yaml` under `nuki.api_token` (or paste it in the web UI's Nuki tab).
5. The bridge IP is shown in the same screen, or use the web UI's Nuki tab → **Discover** to find it automatically.

Alternatively, you can discover the bridge and use its token directly from the web UI (Nuki tab → Discover → fill IP and token → Save).

### Getting the Hue Bridge API key

**Option A — Via the web UI (recommended):**

1. Open the web UI → **Hue tab**.
2. Click **Discover** to find the Hue Bridge IP.
3. **Press the physical button** on top of the Hue Bridge.
4. Click **Pair** within 30 seconds — the API key is generated and saved automatically.

**Option B — Manually via curl:**

```sh
# Press the Hue Bridge button, then run within 30s:
curl -X POST http://<bridge-ip>/api -d '{"devicetype":"nukiblinker"}'
# Response: [{"success":{"username":"<your-api-key>"}}]
```

Copy the `username` value into `secrets.yaml` under `hue.api_key` (or pair from the web UI's Hue tab).

### Speakers not found (discovery returns empty)

Speaker discovery relies on **mDNS/multicast** (zeroconf for Chromecast). If the Discover button returns empty:

- **Verify host networking**: `docker inspect nukiblinker --format '{{.HostConfig.NetworkMode}}'` should return `host`.
- **Speakers are on the same LAN** and powered on.
- **Firewall**: mDNS uses UDP port 5353. Ensure it's not blocked.
- **Port 5353 conflict**: see below.
- **WSL2**: see the WSL2 section below.

**Workaround — use IP addresses**: If discovery doesn't work, you can enter speaker **IP addresses** instead of names in the Speakers tab. IP-based connections bypass mDNS entirely. Find the IP in the Google Home / Apple Home app under device settings.

### Port 5353 conflict (mDNS)

If logs show `"fail to bind 5353"` or `"Address already in use"`, another process on the host already occupies the mDNS port. This blocks both discovery AND name-based playback.

**Immediate fix**: Enter speaker **IP addresses** instead of names. IP-based Chromecast connections use `get_chromecast_from_host()`, which does not require port 5353.

**Root fix** — free port 5353 so HomeKit, discovery, and name-based playback all work:

```powershell
# 1. Check if Apple Bonjour is running
Get-Service -Name "Bonjour Service" -ErrorAction SilentlyContinue
# If present, stop and disable it:
Stop-Service -Name "Bonjour Service"
Set-Service -Name "Bonjour Service" -StartupType Disabled
```

If no Bonjour service is found, the **Windows DNS Client** (`Dnscache`) is occupying port 5353. Disable only its mDNS responder (DNS caching continues to work normally):

```powershell
# Run as Administrator
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Dnscache\Parameters" `
    -Name "EnableMDNS" -Value 0 -PropertyType DWord -Force
# Reboot required
Restart-Computer
```

After reboot, rebuild: `docker compose build && docker compose up -d`.

### WSL2: mDNS and multicast

On Windows with WSL2, `network_mode: host` gives the container access to the WSL2 VM's network — not the Windows host directly. For mDNS (speaker discovery, HomeKit) to work:

1. **Use WSL2 mirrored networking** (recommended). In `%USERPROFILE%\.wslconfig`:
   ```ini
   [wsl2]
   networkingMode=mirrored
   ```
   Then restart WSL: `wsl --shutdown` and reopen. Mirrored mode shares the Windows host's network interfaces, so mDNS packets reach the LAN.

2. **Verify mDNS works** from inside WSL2:
   ```sh
   # Install avahi-utils if needed
   sudo apt install avahi-utils
   avahi-browse -a -t
   ```
   If this shows your Chromecast devices, discovery will work from Docker too.

3. **NAT mode (default WSL2)** does NOT forward multicast. If you can't switch to mirrored mode, speakers won't be discoverable from inside the container. Consider running NukiBlinker directly on the host instead of Docker.

### HomeKit: accessory visible but pairing fails

Discovery uses mDNS (UDP 5353), but **pairing connects over TCP to the HAP port (51826)**. If the accessory appears in the Home app but pairing fails:

1. **Open the HAP port** in the Windows firewall:
   ```powershell
   New-NetFirewallRule -DisplayName "NukiBlinker HAP" -Direction Inbound -Protocol TCP -LocalPort 51826 -Action Allow
   ```

2. **Wrong advertised IP**: on multi-interface hosts (WSL2/Docker), zeroconf may advertise an internal IP (e.g. `172.x`) that the iPhone can't reach. NukiBlinker binds the HAP driver to the same LAN IP used for the Nuki callback. If auto-detection picks the wrong interface, set it explicitly:
   ```yaml
   server:
     public_host: "192.168.1.50"   # your host's LAN IP
   ```
   Verify with `dns-sd -B _hap._tcp` (macOS) or the "Discovery" iOS app — the advertised address must be your LAN IP.

3. **"Incorrect setup code"**: enter the 8 digits of the `XXX-XX-XXX` code shown in the startup log (dashes are not typed on iOS). The auto-generated code is persisted in `{persist_dir}/setup_code` and stays stable across restarts. Apple also rejects trivial codes (`123-45-678`, `111-11-111`, …) — don't configure one of those as `setup_code`.

4. **Stale pairing state**: after failed pairing attempts, delete the persist state and retry:
   ```sh
   rm -rf ./homekit/*   # the mounted persist_dir
   docker compose restart
   ```
   Then remove any half-added accessory from the Home app before pairing again.

> Note: the accessory uses HomeKit category *Sensor* (with a Doorbell service). iOS refuses to pair `Video Doorbell` accessories that have no camera stream — same approach as Homebridge doorbell plugins.

### No logs after test event (nothing happens)

The `ring` event has **audio disabled by default**. If you're testing speakers, use `ring_to_open` or enable audio for `ring` in the Events tab first. Check the startup log for a config summary:

```
[INFO] Config loaded from /app/config.yaml: nuki=192.168.1.100, hue=192.168.1.200, chromecast=2 speakers
```

If integrations show `<not configured>`, the config wasn't saved or loaded correctly.

### DeprecationWarning about `on_event`

Fixed in v0.2.0. Rebuild the image: `docker compose build && docker compose up -d`.

## Development

| Command | Description | Where |
|---|---|---|
| `make lint` | Run flake8 | CI |
| `make test` | Run pytest with coverage | CI |
| `make build` | Build Docker image | Mini PC (prod) |

> **Note**: All testing and linting run in **GitHub Actions CI** only. No testing, linting, Poetry, or Docker on the work laptop — code only.

### Branch workflow (CI as the test gate)

```
push feat/my-branch  →  GitHub Actions runs lint + test
     →  CI green  →  open PR  →  merge to main
```

Verification happens exclusively in CI. Push the branch, let GitHub Actions run
`make lint` + `make test`, read failing job logs, fix, and re-push until CI is green.

### Parallel agents (git worktrees)

To run several agents in parallel without conflicts, give each one its own
**git worktree** — a separate working folder sharing the same `.git`, on its own
branch from `origin/main`. Worktrees live in the sibling folder
`../NukiBlinker-wt/<branch-slug>` and are managed with `script/worktree.ps1`
(`script/worktree.sh` on Linux/WSL2):

```powershell
.\script\worktree.ps1 -Action new    -Branch feat/my-task   # create folder + branch
.\script\worktree.ps1 -Action list                          # list worktrees
.\script\worktree.ps1 -Action remove -Branch feat/my-task   # remove after merge
```

Each agent only edits and pushes its branch — CI remains the sole test gate.
Conflicts surface only at merge time, never between folders. See the `/worktree`
workflow in `.windsurf/workflows/`.

For multi-issue work, the `/orchestrate` workflow takes a list of issue numbers,
auto-decides which are parallel-safe vs sequential, isolates each in a worktree,
implements them, pushes, watches CI, and merges in order — driven from one
command in the orchestrator window.

#### Real parallel runs (one window per issue)

A single Cascade window processes issues sequentially. For genuine wall-clock
parallelism on **independent** issues, use the launcher:

```powershell
.\script\orchestrate-parallel.ps1 -Issues 140,141,142 -Wait   # -Merge to auto-merge
```

It creates a worktree + branch + task brief per issue and **opens one Windsurf
window per issue**. In each new window, type **`/orchestrate-run`** — that agent
reads its `.orchestrate-task.md` and runs autonomously (implement → test → push →
PR → CI green). Cascade can't auto-inject a prompt, so this one paste is required.
With `-Wait` the launcher polls GitHub until every PR is green; with `-Merge` it
then squash-merges in issue order. Linux/WSL2: `script/orchestrate-parallel.sh`.

### Tech Stack

- **Python 3.11+** (Docker image `python:3.14-slim`) · **FastAPI** · **uvicorn** · **httpx** · **pydantic**
- **pychromecast** · **gTTS** · **HAP-python** · **zeroconf**
- **Black** · **flake8** · **pytest** · **pytest-asyncio**
