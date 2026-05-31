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
- **Web UI**: comprehensive tabbed config UI at `http://localhost:8080/` — device discovery, guided pairing, full event rules
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
# Edit config.yaml with your bridge IPs and tokens
docker compose up -d
```

Open `http://localhost:8080/` on the Mini PC to configure via the web UI.

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

Mandatory fields are marked with a red `*`. Changes are saved to `config.yaml` via the fixed save bar.

## Configuration

See `config.example.yaml` for all options. Key sections:

- **nuki** — Bridge IP, port, API token, optional opener/lock ID filters
- **hue** — Bridge IP, API key, light/group IDs
- **speakers** — Chromecast and AirPlay speaker names, volume
- **homekit** — Enable/disable, setup code
- **events** — Per-event rules (ring, ring_to_open, door_opened)
- **server** — Host and port

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
| `/api/hue/pair` | POST | Pair with Hue Bridge (press button first) |
| `/api/hue/lights` | GET | List Hue lights |
| `/api/hue/groups` | GET | List Hue groups |
| `/api/status` | GET | Service status |
| `/api/pause` | POST | Pause service |
| `/api/resume` | POST | Resume service |
| `/api/test/event/{type}` | POST | Fire test event |

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
docker compose pull && docker compose up -d
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
- **Docker networking**: the container uses bridge networking with port mapping. Outgoing connections to the LAN should work. If not, check `docker network inspect bridge` and your firewall rules.

The app starts normally even if callback registration fails — you can re-register later from the web UI (Nuki tab → Register Callback).

### Container starts but callback URL is wrong

When `server.host` is `0.0.0.0`, NukiBlinker auto-detects the LAN IP for the callback URL sent to the Nuki Bridge. If auto-detection picks the wrong IP (e.g., Docker internal IP), set `server.host` to your actual LAN IP:

```yaml
server:
  host: "192.168.1.50"   # Your Mini PC's LAN IP
  port: 8080
```

> **Note**: This also changes the bind address. Use `0.0.0.0` to bind on all interfaces (recommended) and let auto-detection handle the callback URL.

### DeprecationWarning about `on_event`

Fixed in v0.2.0. Pull the latest image: `docker compose pull && docker compose up -d`.

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
