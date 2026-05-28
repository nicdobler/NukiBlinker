# Tech Spec — NukiBlinker

## Architecture Overview

```
nukiblinker/
├── __main__.py              # Entry point — loads config, starts server
├── config.py                # YAML config loading + Pydantic validation + save
├── server.py                # FastAPI app — callback endpoint + web UI API
├── web_ui.py                # Web configuration UI (serves static + API routes)
├── nuki_client.py           # Nuki Bridge HTTP API client (callback registration)
├── hue_client.py            # Philips Hue Bridge API client (light control)
├── google_home_client.py    # Google Home / Chromecast TTS announcements
├── homekit_service.py       # Apple HomeKit doorbell accessory (HAP-python)
├── discovery.py             # Auto-discovery for Nuki, Hue, and Chromecast
├── notifier.py              # Orchestrates all notification channels in parallel
├── logging_config.py        # Structured logging setup
└── static/                  # Web UI frontend (HTML, CSS, JS)
    └── index.html
```

## Runtime

- **Python >= 3.11** (Docker image: `python:3.14.5-slim`)
- **Poetry** for dependency management
- **Docker** for deployment on Mini PC (WSL2), `--network host` for LAN access

### Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | HTTP server (callback + web UI API) |
| `uvicorn[standard]` | ASGI server |
| `httpx` | Async HTTP client (Nuki + Hue bridge APIs) |
| `pyyaml` | Config file parsing |
| `pydantic` | Config validation |
| `pychromecast` | Google Home / Chromecast discovery + casting |
| `gTTS` | Text-to-speech audio generation |
| `HAP-python[QRCode]` | HomeKit accessory protocol |
| `zeroconf` | mDNS for bridge/speaker auto-discovery |

Dev: `black`, `flake8`, `pytest`, `pytest-asyncio`, `pytest-cov`, `httpx` (for `TestClient`).

## Execution Environment

- **Target**: Mini PC running Windows with WSL2/Docker.
- **Network**: `--network host` mode so the container shares the host's LAN IP.
- **Persistence**: `config.yaml` is read-write (web UI saves to it). Mounted as a volume.

### Development Environments

| Environment | Role |
|---|---|
| Work laptop (Windows) | Code only. No testing, no Poetry, no Docker. |
| Personal Mac | `make test` + `make lint` (unit tests, mocked). `make runLocal` for real-device testing. |
| GitHub Actions | CI/CD: lint → test → build Docker → push to GHCR. |
| Mini PC (Windows + WSL2) | Production: `docker compose pull && up -d`. |

### Testing on Mac

- **`make test`** — Unit/integration tests with mocked HTTP. No real devices needed.
- **`make runLocal`** — Real-device testing. Direct LAN access, mDNS works, HomeKit advertising works. Best for end-to-end validation.
- **`make build`** — Verify Docker image builds. Note: `--network host` doesn't work on Docker for Mac (runs in a Linux VM), so use `make runLocal` for device testing.

## Event Flow

```mermaid
sequenceDiagram
    participant V as Visitor
    participant NO as Nuki Opener
    participant NB as Nuki Bridge
    participant NK as NukiBlinker
    participant HB as Hue Bridge
    participant GH as Google Home
    participant HK as HomeKit

    V->>NO: Presses doorbell
    NO->>NB: Ring detected (state=7)
    NB->>NK: HTTP POST /nuki/callback
    NK-->>NB: 200 OK (immediate)

    par Notification channels (parallel)
        NK->>HB: PUT /lights/{id}/state (blink)
        HB-->>NK: 200
    and
        NK->>GH: Cast TTS audio
    and
        NK->>HK: Doorbell press event
        HK-->>HK: Push to all Apple devices
    end
```

## Component Design

### Config (`config.py`)

Pydantic models validate the YAML config. Supports both load and save (web UI writes back).

```python
class NukiConfig(BaseModel):
    bridge_ip: str = ""
    bridge_port: int = 8080
    api_token: str = ""
    opener_id: int | None = None

class HueConfig(BaseModel):
    bridge_ip: str = ""
    api_key: str = ""
    lights: list[int] = []
    groups: list[int] = []

class CustomBlinkConfig(BaseModel):
    hue: int = 0                  # 0-65535
    saturation: int = 254         # 0-254
    brightness: int = 254         # 1-254
    flashes: int = 3
    interval_ms: int = 500

class BlinkConfig(BaseModel):
    mode: str = "alert"           # "alert" or "custom"
    custom: CustomBlinkConfig = CustomBlinkConfig()

class GoogleHomeConfig(BaseModel):
    enabled: bool = False
    speakers: list[str] = []      # speaker names or IPs
    message: str = "Someone is at the door"
    volume: float = 0.5           # 0.0-1.0

class HomeKitConfig(BaseModel):
    enabled: bool = False
    setup_code: str = ""          # auto-generated if empty
    persist_dir: str = ".homekit" # HAP-python state directory

class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080

class AppConfig(BaseModel):
    nuki: NukiConfig = NukiConfig()
    hue: HueConfig = HueConfig()
    blink: BlinkConfig = BlinkConfig()
    google_home: GoogleHomeConfig = GoogleHomeConfig()
    homekit: HomeKitConfig = HomeKitConfig()
    server: ServerConfig = ServerConfig()
```

All fields have defaults → the service can start with an empty/missing `config.yaml` and be configured entirely via the web UI.

### Server (`server.py`)

FastAPI app:

- **`POST /nuki/callback`** — Receives Nuki Bridge callback payloads.
  - Validates `deviceType == 2` (Opener) and `state == 7` (ring detected).
  - Optionally filters by `nukiId` if `opener_id` is configured.
  - On valid ring: triggers notifier asynchronously.
  - Returns 200 immediately (Nuki Bridge expects fast response).

- **`GET /health`** — Health check endpoint.

- **Web UI routes** — Mounted from `web_ui.py` (see below).

### Web UI (`web_ui.py`)

Serves the configuration page and provides API endpoints for it.

**Access control middleware**: Checks `request.client.host` against `127.0.0.1` / `::1`. Returns `403 Forbidden` for any other IP.

**API routes** (all under `/api/`):

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/config` | Return current config (secrets masked) |
| PUT | `/api/config` | Save updated config → `config.yaml` |
| GET | `/api/discover/nuki` | Auto-discover Nuki Bridges |
| GET | `/api/discover/hue` | Auto-discover Hue Bridges |
| GET | `/api/discover/speakers` | Auto-discover Chromecast speakers |
| GET | `/api/hue/lights` | List available Hue lights and groups |
| POST | `/api/hue/pair` | Initiate Hue Bridge pairing (press button flow) |
| POST | `/api/test/blink` | Trigger test blink |
| POST | `/api/test/announce` | Trigger test Google Home announcement |
| POST | `/api/test/homekit` | Trigger test HomeKit doorbell notification |
| GET | `/api/status` | Bridge connectivity, last ring, uptime |
| GET | `/api/homekit/setup-code` | Return HomeKit pairing code + QR data |

**Static files**: `index.html` — single-page app (vanilla JS or lightweight framework). Served at `/`.

### Nuki Client (`nuki_client.py`)

Manages the Nuki Bridge HTTP API:

- **`register_callback(callback_url)`** — `GET /callback/add?url=<url>&token=<token>`.
  - Lists existing callbacks first to avoid duplicates.
- **`list_callbacks()`** — Returns current registered callbacks.
- **`remove_callback(callback_id)`** — Removes a callback by ID.
- **`list_openers()`** — Returns paired Openers (for the web UI picker).

### Hue Client (`hue_client.py`)

Manages the Philips Hue Bridge v1 REST API:

- **`trigger_alert(light_ids, group_ids)`** — Sends `{"alert": "lselect"}`.
- **`get_light_state(light_id)`** — Reads current state.
- **`set_light_state(light_id, state)`** — Sets light to a specific state.
- **`trigger_custom_blink(light_ids, config)`** — Save → flash loop → restore.
- **`list_lights()`** — Returns all lights (for web UI picker).
- **`list_groups()`** — Returns all groups (for web UI picker).
- **`pair()`** — Creates API key via `POST /api {"devicetype":"nukiblinker"}`.

Uses `httpx.AsyncClient` for non-blocking HTTP calls.

### Google Home Client (`google_home_client.py`)

Manages Chromecast-protocol speakers:

- **`announce(speaker_names, message, volume)`** — For each speaker:
  1. Generate TTS audio via `gTTS` → save as temp `.mp3`.
  2. Connect via `pychromecast`.
  3. Set volume → cast audio → restore volume.
- **`list_speakers()`** — Discover Chromecast devices on LAN via `pychromecast.get_chromecasts()`.

TTS audio is cached in memory (same message doesn't regenerate).

### HomeKit Service (`homekit_service.py`)

Exposes a virtual HomeKit doorbell accessory:

- Uses `HAP-python` to create a `Doorbell` accessory.
- **`start()`** — Starts the HAP accessory driver (runs in a background thread).
- **`trigger_ring()`** — Fires the doorbell `ProgrammableSwitchEvent` → all paired Apple devices receive a notification.
- **`get_setup_code()`** — Returns the 8-digit setup code for pairing.
- **`get_qr_code()`** — Returns QR code data (base64 PNG) for the web UI.
- **`is_paired()`** — Whether any Apple device has paired.

State (pairing keys) persisted in `config.homekit.persist_dir`.

### Discovery (`discovery.py`)

Auto-discovery for devices on the LAN:

```python
async def discover_nuki_bridges() -> list[dict]:
    """Nuki Cloud endpoint or local UDP broadcast."""

async def discover_hue_bridges() -> list[dict]:
    """mDNS (_hue._tcp.local) or discovery.meethue.com."""

async def discover_chromecast_speakers() -> list[dict]:
    """pychromecast / zeroconf scan."""
```

Each returns a list of `{"name": ..., "ip": ..., "port": ...}`.

### Notifier (`notifier.py`)

Replaces the old `blinker.py`. Orchestrates all notification channels in parallel:

```python
async def notify(config, hue_client, google_home_client, homekit_service):
    tasks = []

    # Hue lights (always enabled if lights/groups configured)
    if config.hue.lights or config.hue.groups:
        tasks.append(trigger_hue(hue_client, config))

    # Google Home (opt-in)
    if config.google_home.enabled and config.google_home.speakers:
        tasks.append(trigger_google_home(google_home_client, config.google_home))

    # HomeKit (opt-in)
    if config.homekit.enabled:
        tasks.append(trigger_homekit(homekit_service))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    # Log failures but never crash
    for r in results:
        if isinstance(r, Exception):
            logger.warning("Notification channel failed: %s", r)
```

### Entry Point (`__main__.py`)

```mermaid
flowchart TD
    A[Parse CLI args] --> B[Load config.yaml]
    B --> C[Validate config]
    C --> D[Configure logging]
    D --> E{HomeKit enabled?}
    E -->|Yes| F[Start HAP driver in background thread]
    E -->|No| G[Skip]
    F --> H[Register Nuki callback idempotent]
    G --> H
    H --> I[Start FastAPI + uvicorn]
```

1. Parse CLI args (`--config config.yaml`).
2. Load and validate config (defaults allow empty config).
3. Configure logging.
4. If HomeKit enabled: start HAP accessory driver in a background thread.
5. Register callback on Nuki Bridge (idempotent). Skip if Nuki not configured yet.
6. Start FastAPI/uvicorn server (callback endpoint + web UI).

## Nuki Bridge Callback Payload

```json
{
    "nukiId": 12345,
    "deviceType": 2,
    "mode": 2,
    "state": 7,
    "stateName": "ring to open",
    "batteryCritical": false
}
```

Key fields:
- `deviceType`: 0=SmartLock, 2=Opener
- `state`: 7=ring detected on Opener

## External API Reference

### Hue Bridge v1 REST

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api` | Create API key (pairing) |
| GET | `/api/{key}/lights` | List all lights |
| GET | `/api/{key}/lights/{id}` | Read light state |
| PUT | `/api/{key}/lights/{id}/state` | Set light state |
| GET | `/api/{key}/groups` | List all groups |
| PUT | `/api/{key}/groups/{id}/action` | Set group action |

### Nuki Bridge HTTP API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/list` | List paired devices |
| GET | `/callback/list` | List registered callbacks |
| GET | `/callback/add?url=&token=` | Register callback |
| GET | `/callback/remove?id=` | Remove callback |

### Chromecast Protocol

Via `pychromecast` — no direct HTTP. Library handles mDNS discovery, connection, and media casting.

### HomeKit Accessory Protocol

Via `HAP-python` — no direct HTTP. Library handles mDNS advertising, pairing, and event dispatch.

## Web UI Architecture

```mermaid
flowchart LR
    subgraph Browser [Browser - localhost only]
        UI[index.html - SPA]
    end

    subgraph NukiBlinker
        WUI[web_ui.py - API routes]
        CFG[config.py]
        DISC[discovery.py]
        HC[hue_client.py]
        GHC[google_home_client.py]
        HKS[homekit_service.py]
    end

    UI -->|GET /api/config| WUI
    UI -->|PUT /api/config| WUI
    UI -->|GET /api/discover/*| WUI
    UI -->|POST /api/test/*| WUI
    WUI --> CFG
    WUI --> DISC
    WUI --> HC
    WUI --> GHC
    WUI --> HKS
    CFG -->|read/write| YAML[(config.yaml)]
```

The frontend is a single `index.html` with embedded CSS/JS (no build step, no npm). Communicates with the backend via JSON API calls.

## CI/CD

- **GitHub Actions** (`.github/workflows/ci.yml`):
  - On push/PR: lint (flake8) + test (pytest).
  - On merge to `main`: build Docker image + push to `ghcr.io/<owner>/nukiblinker:latest` (also tagged by commit SHA).
- **Dependabot** (`.github/dependabot.yml`): auto-updates for pip, GitHub Actions, and Docker.
- **GHCR**: GitHub Container Registry. Image is public. No secrets needed on the Mini PC to pull.

## Testing

All tests run via `make test` on the Mac. Real-device testing via `make runLocal`.

| Test file | Covers |
|---|---|
| `tests/test_config.py` | Config validation, load, save, defaults |
| `tests/test_server.py` | Callback endpoint (valid ring, wrong device, wrong state) |
| `tests/test_web_ui.py` | Web UI API routes + localhost access control (403) |
| `tests/test_hue_client.py` | Hue API calls (mock httpx) |
| `tests/test_nuki_client.py` | Callback registration (mock httpx) |
| `tests/test_google_home.py` | TTS generation + Chromecast casting (mock pychromecast) |
| `tests/test_homekit.py` | HAP accessory lifecycle (mock HAP-python) |
| `tests/test_notifier.py` | Parallel channel dispatch, failure isolation |
| `tests/test_discovery.py` | Auto-discovery responses (mock zeroconf) |

## Docker

```dockerfile
FROM python:3.14.5-slim
# Poetry install → copy source → EXPOSE 8080 → ENTRYPOINT
```

### Production deployment (Mini PC)

```yaml
services:
  nukiblinker:
    image: ghcr.io/nicdobler/nukiblinker:latest
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml       # read-write for web UI
      - ./homekit:/app/.homekit               # HomeKit pairing state
```

Deploy/update:

```sh
docker compose pull && docker compose up -d
```

### Local testing (Mac)

```sh
make runLocal    # best for real-device testing (direct LAN + mDNS)
make build       # verify Docker image builds
```

## Logging

- Structured logging via Python `logging` module.
- Console output (INFO level by default).
- Rotating file log (`logs/nukiblinker.log`), configurable retention.
- Key events logged: startup, callback received, ring detected, channel triggered, channel failure, config saved.
