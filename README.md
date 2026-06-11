# NukiBlinker

Reacts to Nuki doorbell and Smart Lock events with configurable notifications: Hue light blinks, voice announcements on Google Nest and Apple HomePod, and Apple HomeKit doorbell push notifications.

## Features

- **3 event types**: Ring (unknown visitor), Ring to Open (authorized), Door Opened (Smart Lock)
- **Per-event rules**: each event gets its own blink pattern, audio, and HomeKit toggle
- **Personalized announcements**: "{name} llegó a casa" via Nuki activity log
- **Hue light blinks**: alert mode (built-in 15s) or custom (color, flash count, interval)
- **Voice announcements**: TTS via gTTS on Google Nest (Chromecast) and Apple HomePod (AirPlay 2)
- **Chime sounds**: bundled audio files for door-opened events
- **Apple HomeKit**: virtual doorbell accessory — notifications on all paired Apple devices
- **Event validation**: configurable timestamp validation to reject stale events
- **Event logging**: comprehensive event history with detailed action tracking and CSV export
- **Night mode**: time-based notification adjustments (no audio, dimmer lights)
- **Web UI**: comprehensive tabbed config UI at `http://localhost:8080/` — device discovery, guided pairing, full event rules, event log viewer
- **Auto-discovery**: Nuki Bridge, Hue Bridge, Chromecast, and AirPlay speakers
- **Graceful lifecycle**: shutdown deregisters Nuki callback, pause/resume via web UI

## Prerequisites

- **Nuki Opener** and/or **Smart Lock** connected to a **Nuki Bridge**
- **Philips Hue Bridge** on the same LAN
- **Docker** (recommended), or **Python >= 3.11** + [Poetry](https://python-poetry.org/)
- Optional: Google Nest / Chromecast speakers, Apple HomePod

## Quick Start

```sh
cp config.example.yaml config.yaml
docker compose up -d
```

Open `http://localhost:8080/` on the Mini PC to configure via the web UI.

## Initial Setup Guide

After starting the container, open the web UI and follow these steps in order:

### 1. Connect the Nuki Bridge

Go to the **Nuki** tab.

1. Click **Discover** to find your Nuki Bridge on the LAN, or enter the IP manually.
2. Enter the **API Token** (find it in the Nuki app → Settings → Manage Bridge → Enable API).
3. Click **Save** in the bottom bar.
4. Click **Register Callback** — this tells the Bridge to send events (ring, door open) to NukiBlinker.
5. Optionally, click **List Devices** and click on a device to filter events to a specific Opener or Smart Lock.

### 2. Connect the Hue Bridge

Go to the **Hue** tab.

1. Click **Discover** to find the Hue Bridge IP, or enter it manually.
2. **Press the physical button** on top of the Hue Bridge.
3. Click **Pair** within 30 seconds — the API key is generated and saved automatically.
4. Click **List Lights** and/or **List Groups** — click on the ones you want to blink on events.
5. Click **Save**.

### 3. Add speakers (optional)

Go to the **Speakers** tab.

1. Click **Discover** under Chromecast or AirPlay to find speakers on the network.
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

- **Blink mode**: `alert` (15s Hue built-in), `custom` (set color, flash count, interval), or `none`.
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
| **Nuki** | Bridge connection, network discovery, callback registration, device filter (opener/lock ID) |
| **Hue** | Bridge connection, network discovery, guided pairing (button press → pair), light & group selection |
| **Speakers** | Chromecast & AirPlay names, network discovery, volume slider |
| **HomeKit** | Enable/disable, setup code, persist directory |
| **Events** | Per-event blink (alert/custom HSB), audio (TTS/chime), HomeKit toggle |
| **Event Log** | View event history, export CSV, clear log |
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
- In-memory storage with configurable retention
- Optional file persistence for durability
- Detailed action tracking with processing times
- CSV export for analysis
- Web UI viewer with pagination and search

#### Night Mode
Reduces notifications during specified hours:
- Configurable time windows (default: 22:00-07:00)
- Grace periods for smooth transitions
- Audio suppression during night hours
- Reduced light brightness (configurable factor)
- HomeKit notifications preserved for security

## Configuration

See `config.example.yaml` for all options. Key sections:

- **nuki** — Bridge IP, port, API token, optional opener/lock ID filters
- **hue** — Bridge IP, API key, light/group IDs
- **speakers** — Chromecast and AirPlay speaker names, volume
- **homekit** — Enable/disable, setup code
- **events** — Per-event rules (ring, ring_to_open, door_opened)
- **event_validation** — Timestamp validation settings
- **night_mode** — Quiet hours and notification adjustments
- **event_log** — Logging configuration and retention
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
  max_entries: 1000       # Maximum events in memory
  retention_days: 7       # How long to keep events
  persist_to_file: true   # Save to disk for durability
  file_path: "logs/event_log.json"
```

### Getting API Keys

- **Nuki Bridge**: Nuki app → Settings → Manage Bridge → Enable API. Note the token. Or use the Web UI's Nuki tab.
- **Hue Bridge**: Use the Web UI's Hue tab (Discover → press bridge button → Pair), or manually: `POST http://<bridge-ip>/api {"devicetype":"nukiblinker"}`.

### API Endpoints (Web UI)

| Endpoint | Method | Description |
|---|---|---|
| `/api/config` | GET/PUT | Read/write full configuration |
| `/api/discover/nuki` | GET | Discover Nuki Bridges on LAN |
| `/api/discover/hue` | GET | Discover Hue Bridges on LAN |
| `/api/discover/speakers` | GET | Discover Chromecast & AirPlay speakers |
| `/api/nuki/pair` | POST | Register callback on Nuki Bridge |
| `/api/nuki/devices` | GET | List Nuki devices |
| `/api/nuki/callbacks` | GET | List registered callbacks |
| `/api/hue/status` | GET | Check Hue Bridge connection & API key validity |
| `/api/hue/pair` | POST | Pair with Hue Bridge (tries existing key first) |
| `/api/hue/lights` | GET | List Hue lights |
| `/api/hue/groups` | GET | List Hue groups |
| `/api/status` | GET | Service status |
| `/api/pause` | POST | Pause service |
| `/api/resume` | POST | Resume service |
| `/api/test/event/{type}` | POST | Fire test event |
| `/api/events/log` | GET | Get paginated event log |
| `/api/events/export` | GET | Export event log as CSV |
| `/api/events/clear` | POST | Clear all event log entries |
| `/api/config/event-validation` | GET/PUT | Event validation configuration |
| `/api/config/night-mode` | GET/PUT | Night mode configuration |
| `/api/config/event-log` | GET/PUT | Event logging configuration |

## Deployment (Mini PC)

### First-time setup

```sh
mkdir -p nukiblinker && cd nukiblinker
# Copy docker-compose.yml and config.example.yaml from the repo
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your Nuki Bridge IP/token and Hue Bridge IP/key (or configure later via the web UI).

### Start / update

```sh
docker compose build && docker compose up -d
```

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
4. The app shows the **API token** — copy it into `config.yaml` under `nuki.api_token`.
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

Copy the `username` value into `config.yaml` under `hue.api_key`.

### Speakers not found (discovery returns empty)

Speaker discovery relies on **mDNS/multicast** (zeroconf for Chromecast, pyatv for AirPlay). If the Discover button returns empty:

- **Verify host networking**: `docker inspect nukiblinker --format '{{.HostConfig.NetworkMode}}'` should return `host`.
- **Speakers are on the same LAN** and powered on.
- **Firewall**: mDNS uses UDP port 5353. Ensure it's not blocked.
- **Port 5353 conflict**: see below.
- **WSL2**: see the WSL2 section below.

**Workaround — use IP addresses**: If discovery doesn't work, you can enter speaker **IP addresses** instead of names in the Speakers tab. IP-based connections bypass mDNS entirely. Find the IP in the Google Home / Apple Home app under device settings.

### Port 5353 conflict (mDNS)

If logs show `"fail to bind 5353"` or `"Address already in use"`, another process on the host already occupies the mDNS port. This blocks both discovery AND name-based playback.

**Immediate fix**: Enter speaker **IP addresses** instead of names. IP-based Chromecast connections use `get_chromecast_from_host()` and AirPlay uses unicast scanning — neither requires port 5353.

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
   If this shows your Chromecast/HomePod devices, discovery will work from Docker too.

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

3. **Stale pairing state**: after failed pairing attempts, delete the persist state and retry:
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
| `make test` | Run pytest with coverage | Mac / CI |
| `make lint` | Run flake8 | Mac / CI |
| `make format` | Show Black diff | Mac |
| `make install` | Install/update deps | Mac |
| `make runLocal` | Run locally (real devices) | Mac |
| `make build` | Build Docker image | Mac |

> **Note**: No testing or building on the work laptop. Code only.

### Tech Stack

- **Python 3.14** · **FastAPI** · **uvicorn** · **httpx** · **pydantic**
- **pychromecast** · **pyatv** · **gTTS** · **HAP-python** · **zeroconf**
- **Black** · **flake8** · **pytest** · **pytest-asyncio**
