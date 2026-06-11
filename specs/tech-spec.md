# Tech Spec — NukiBlinker

## Architecture Overview

```
nukiblinker/
├── __main__.py              # Entry point — loads config, starts server
├── config.py                # YAML config loading + Pydantic validation + save
├── server.py                # FastAPI app — callback endpoint + web UI API
├── web_ui.py                # Web configuration UI (serves static + API routes)
├── event_router.py          # Classifies Nuki events and dispatches to matching rule
├── nuki_client.py           # Nuki Bridge HTTP API client (callback registration)
├── hue_client.py            # Philips Hue Bridge API client (light control)
├── chromecast_client.py     # Google Nest / Chromecast audio playback
├── airplay_client.py        # Apple HomePod AirPlay 2 audio playback
├── audio.py                 # Audio generation (TTS + chime selection)
├── homekit_service.py       # Apple HomeKit doorbell accessory (HAP-python)
├── discovery.py             # Auto-discovery for Nuki, Hue, Chromecast, AirPlay
├── notifier.py              # Orchestrates notification channels per event rule
├── logging_config.py        # Structured logging setup
├── sounds/                  # Bundled chime audio files
│   └── chime.mp3              # Default doorbell chime
└── static/                  # Web UI frontend (HTML, CSS, JS)
    └── index.html
```

## Runtime

- **Python >= 3.11** (Docker image: `python:3.14.5-slim`)
- **Poetry** for dependency management
- **Docker** for deployment on Mini PC (WSL2), port mapping for LAN access

### Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | HTTP server (callback + web UI API) |
| `uvicorn[standard]` | ASGI server |
| `httpx` | Async HTTP client (Nuki + Hue bridge APIs) |
| `pyyaml` | Config file parsing |
| `pydantic` | Config validation |
| `pychromecast` | Google Nest / Chromecast discovery + casting |
| `pyatv` | Apple HomePod / AirPlay 2 discovery + streaming |
| `gTTS` | Text-to-speech audio generation |
| `HAP-python[QRCode]` | HomeKit accessory protocol |
| `zeroconf` | mDNS for bridge/speaker auto-discovery |

Dev: `black`, `flake8`, `pytest`, `pytest-asyncio`, `pytest-cov`, `httpx` (for `TestClient`).

## Execution Environment

- **Target**: Mini PC running Windows with WSL2/Docker.
- **Network**: Host networking (`network_mode: host`). Container shares the host's network stack directly. Required for mDNS/multicast (speaker discovery, HomeKit advertising). On WSL2, mirrored networking mode is recommended for full LAN multicast support.
- **Persistence**: `config.yaml` is read-write (web UI saves to it). Mounted as a volume. Save operations include read-back verification to detect silent write failures.
- **Startup diagnostics**: Logs a config summary at startup showing which integrations are configured (e.g., `nuki=192.168.1.100, hue=<not configured>`).

### Development Environments

| Environment | Role |
|---|---|
| Work laptop (Windows) | Code only. No testing, no Poetry, no Docker. |
| Personal Mac | `make test` + `make lint` (unit tests, mocked). `make runLocal` for real-device testing. |
| GitHub Actions | CI: lint → test. |
| Mini PC (Windows + WSL2) | Production: `git pull && docker compose build && up -d`. |

### Testing on Mac

- **`make test`** — Unit/integration tests with mocked HTTP. No real devices needed.
- **`make runLocal`** — Real-device testing. Direct LAN access, mDNS works, HomeKit advertising works. Best for end-to-end validation.
- **`make build`** — Verify Docker image builds. Use `make runLocal` for real-device testing.

## Event Flow

```mermaid
sequenceDiagram
    participant V as Visitor
    participant NO as Nuki Opener
    participant NB as Nuki Bridge
    participant NK as NukiBlinker
    participant ER as EventRouter
    participant HB as Hue Bridge
    participant GN as Google Nest
    participant HP as HomePod
    participant HK as HomeKit

    V->>NO: Presses doorbell
    NO->>NB: State change
    NB->>NK: HTTP POST /nuki/callback
    NK-->>NB: 200 OK (immediate)
    NK->>ER: Classify event

    alt Ring (no open) — Opener
        ER->>ER: Match "ring" rule
        par
            ER->>HB: Blink (warning pattern)
        and
            ER->>HK: Doorbell notification
        end

    else Ring to open — Opener
        ER->>ER: Match "ring_to_open" rule
        par
            ER->>HB: Blink (welcome pattern)
        and
            ER->>GN: TTS "Nico ha llegado a casa"
        and
            ER->>HP: TTS "Nico ha llegado a casa"
        and
            ER->>HK: Doorbell notification
        end

    else Door opened — Smart Lock
        ER->>ER: Match "door_opened" rule
        par
            ER->>GN: Play chime
        and
            ER->>HP: Play chime
        end
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
    opener_id: int | None = None   # filter Opener events by nukiId
    lock_id: int | None = None     # filter Smart Lock events by nukiId

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
    mode: str = "alert"           # "alert", "custom", or "none"
    custom: CustomBlinkConfig = CustomBlinkConfig()

class SpeakersConfig(BaseModel):
    chromecast: list[str] = []    # Google Nest / Chromecast speaker names
    airplay: list[str] = []       # HomePod / AirPlay speaker names
    volume: float = 0.5           # 0.0-1.0

class AudioConfig(BaseModel):
    enabled: bool = False
    mode: str = "tts"              # "tts", "chime", or "none"
    message: str = "{name} llegó a casa"  # template, supports {name}
    chime: str = "chime.mp3"       # filename in sounds/ (when mode="chime")
    fallback_name: str = "Alguien" # used when {name} can't be resolved

class EventRuleConfig(BaseModel):
    blink: BlinkConfig = BlinkConfig()
    audio: AudioConfig = AudioConfig()
    homekit: bool = True

class EventRulesConfig(BaseModel):
    ring: EventRuleConfig = EventRuleConfig(
        blink=BlinkConfig(mode="alert"),
        audio=AudioConfig(enabled=False),
        homekit=True,
    )
    ring_to_open: EventRuleConfig = EventRuleConfig(
        blink=BlinkConfig(mode="custom"),
        audio=AudioConfig(enabled=True, mode="tts", message="Nico ha llegado a casa"),
        homekit=True,
    )
    door_opened: EventRuleConfig = EventRuleConfig(
        blink=BlinkConfig(mode="none"),
        audio=AudioConfig(enabled=True, mode="chime"),
        homekit=False,
    )

class HomeKitConfig(BaseModel):
    enabled: bool = False
    setup_code: str = ""          # auto-generated if empty
    persist_dir: str = ".homekit" # HAP-python state directory
    address: str = ""             # LAN IP to bind/advertise; falls back to get_public_host()

class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080

class AppConfig(BaseModel):
    nuki: NukiConfig = NukiConfig()
    hue: HueConfig = HueConfig()
    speakers: SpeakersConfig = SpeakersConfig()
    homekit: HomeKitConfig = HomeKitConfig()
    events: EventRulesConfig = EventRulesConfig()
    server: ServerConfig = ServerConfig()
```

All fields have defaults → the service can start with an empty/missing `config.yaml` and be configured entirely via the web UI.

### Server (`server.py`)

FastAPI app:

- **`POST /nuki/callback`** — Receives Nuki Bridge callback payloads.
  - Accepts `deviceType == 0` (Smart Lock) and `deviceType == 2` (Opener).
  - Optionally filters by `nukiId` using `opener_id` or `lock_id`.
  - Passes payload to `event_router.classify()` to determine event type.
  - Dispatches to the matching event rule's notification channels.
  - Returns 200 immediately (Nuki Bridge expects fast response).

- **`GET /health`** — Health check endpoint.

- **Web UI routes** — Mounted from `web_ui.py` (see below).

### Web UI (`web_ui.py`)

Serves the configuration page and provides API endpoints for it.

**Access control middleware** (`PrivateNetworkMiddleware`): Uses `ipaddress.ip_address(client_ip).is_private` to allow requests from localhost, Docker gateway (172.x), and LAN IPs. Returns `403 Forbidden` for public IPs.

**API routes** (all under `/api/`):

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/config` | Return current config (secrets masked) |
| PUT | `/api/config` | Save updated config → `config.yaml` |
| GET | `/api/discover/nuki` | Auto-discover Nuki Bridges |
| GET | `/api/discover/hue` | Auto-discover Hue Bridges |
| GET | `/api/discover/speakers` | Auto-discover Chromecast + AirPlay speakers |
| POST | `/api/nuki/pair` | Register callback on Nuki Bridge |
| GET | `/api/nuki/devices` | List Nuki devices (Openers + Smart Locks) |
| GET | `/api/nuki/callbacks` | List registered callbacks on Bridge |
| GET | `/api/hue/status` | Check Hue Bridge connection and API key validity |
| POST | `/api/hue/pair` | Pair with Hue Bridge (validates existing key first) |
| GET | `/api/hue/lights` | List available Hue lights |
| GET | `/api/hue/groups` | List available Hue groups |
| POST | `/api/test/event/{type}` | Fire all channels for a specific event rule |
| GET | `/api/status` | Service status, last event |
| POST | `/api/pause` | Deregister Nuki callback (keep service running) |
| POST | `/api/resume` | Re-register Nuki callback |

**Static files**: `index.html` — single-page app (vanilla JS or lightweight framework). Served at `/`.

### Nuki Client (`nuki_client.py`)

Manages the Nuki Bridge HTTP API:

- **`register_callback(callback_url)`** — `GET /callback/add?url=<url>&token=<token>`.
  - Lists existing callbacks first to avoid duplicates.
- **`list_callbacks()`** — Returns current registered callbacks.
- **`remove_callback(callback_id)`** — Removes a callback by ID.
- **`list_devices()`** — Returns paired devices (Openers + Smart Locks, for the web UI picker).
- **`get_last_log(nuki_id, count=1)`** — `GET /log?nukiId=<id>&count=1&token=<token>`. Returns the latest activity log entry, including the `name` of the user who triggered the action.

### Hue Client (`hue_client.py`)

Manages the Philips Hue Bridge v1 REST API:

- **`check_connection()`** — Validates API key by reading bridge config (`GET /api/{key}/config`). Returns `{connected, name, error}`.
- **`trigger_alert(light_ids, group_ids)`** — Sends `{"alert": "lselect"}`.
- **`get_light_state(light_id)`** — Reads current state.
- **`set_light_state(light_id, state)`** — Sets light to a specific state.
- **`trigger_custom_blink(light_ids, config)`** — Save → flash loop → restore.
- **`list_lights()`** — Returns all lights (for web UI picker).
- **`list_groups()`** — Returns all groups (for web UI picker).
- **`pair()`** — Creates API key via `POST /api {"devicetype":"nukiblinker"}`.

Uses `httpx.AsyncClient` for non-blocking HTTP calls.

### Audio (`audio.py`)

Generates or selects audio files for playback:

- **`render_message(template, context)`** — Replaces `{name}` (and future variables) in the template. Falls back to `fallback_name` if `name` is not available.
- **`get_audio(audio_config: AudioConfig, context: dict) -> Path`** — Returns path to an `.mp3` file:
  - `mode="tts"`: renders template → generates via `gTTS`, caches by rendered message hash.
  - `mode="chime"`: returns `sounds/{chime_filename}`.
- TTS cache is in-memory (same rendered message doesn’t regenerate).
- Bundled chimes ship in `nukiblinker/sounds/` (included in Docker image).

### Chromecast Client (`chromecast_client.py`)

Manages Google Nest / Chromecast speakers:

- **`play(speaker_names, audio_path, volume)`** — For each speaker:
  1. Connect via `pychromecast`.
  2. Set volume → cast audio → restore volume.
- **`list_speakers()`** — Discover Chromecast devices on LAN.

### AirPlay Client (`airplay_client.py`)

Manages Apple HomePod / AirPlay 2 speakers:

- **`play(speaker_names, audio_path, volume)`** — For each speaker:
  1. Connect via `pyatv` (AirPlay 2).
  2. Stream audio → wait for completion.
- **`list_speakers()`** — Discover AirPlay devices on LAN via `pyatv.scan()`.

### HomeKit Service (`homekit_service.py`)

Exposes a virtual HomeKit doorbell accessory:

- Uses `HAP-python` to create a `Doorbell` accessory with category `CATEGORY_SENSOR` — **not** `CATEGORY_VIDEO_DOOR_BELL`, since iOS refuses to pair a video doorbell that lacks a camera RTP stream service (same pattern as Homebridge doorbell plugins without camera).
- The HAP driver binds and advertises on the LAN address resolved by `get_public_host()` (`server.public_host` config, or auto-detect) — the same IP used for the Nuki callback URL. On multi-interface hosts (WSL2/Docker), zeroconf auto-selection may advertise an unreachable internal IP, which makes discovery or pairing fail.
- **`start()`** — Starts the HAP accessory driver (runs in a background thread).
- **`trigger_ring()`** — Fires the doorbell `ProgrammableSwitchEvent` → all paired Apple devices receive a notification.
- **`get_setup_code()`** — Returns the 8-digit setup code for pairing. When not set in config, the generated code is persisted to `{persist_dir}/setup_code` and reused on every restart (HAP-python stores the pincode in `accessory.state`, so the code must be stable). Generated codes skip the trivial codes Apple rejects (`000-00-000` … `999-99-999`, `123-45-678`, `876-54-321`).
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

async def discover_airplay_speakers() -> list[dict]:
    """pyatv / zeroconf scan for AirPlay 2 devices."""
```

Each returns a list of `{"name": ..., "ip": ..., "port": ..., "type": "chromecast"|"airplay"}`.

### Event Router (`event_router.py`)

Classifies Nuki callback payloads into event types and dispatches to the matching rule:

```python
def classify(payload: dict) -> str | None:
    """Returns 'ring', 'ring_to_open', or 'door_opened'. None if ignored."""
    device_type = payload.get("deviceType")
    state = payload.get("state")

    if device_type == 2:     # Opener
        # state=7 → ring_to_open; ring without opening → ring
        ...
    elif device_type == 0:   # Smart Lock
        # state=5 (unlatched) → door_opened (state=3 unlocked is ignored — #60)
        ...
    return None              # unknown device type

async def resolve_person(payload: dict, nuki_client) -> dict:
    """Query Nuki Bridge /log to get the user name for the event.
    Returns context dict: {"name": "Nico"} or {"name": fallback}."""
    nuki_id = payload.get("nukiId")
    try:
        log = await nuki_client.get_last_log(nuki_id)
        return {"name": log.get("name", config.fallback_name)}
    except Exception:
        return {"name": config.fallback_name}

async def dispatch(event_type: str, payload: dict, config: AppConfig, clients: Clients):
    """Looks up config.events[event_type], resolves person, fires channels."""
    rule = getattr(config.events, event_type)
    context = {}
    if event_type in ("ring_to_open", "door_opened"):
        context = await resolve_person(payload, clients.nuki)
    await notifier.notify(rule, config, clients, context)
```

### Notifier (`notifier.py`)

Orchestrates notification channels for a given event rule:

```python
async def notify(rule: EventRuleConfig, config: AppConfig, clients: Clients, context: dict = None):
    tasks = []

    # Hue lights (per-event blink pattern)
    if rule.blink.mode != "none" and (config.hue.lights or config.hue.groups):
        tasks.append(trigger_hue(clients.hue, config.hue, rule.blink))

    # Audio (chime or TTS, per-event, with {name} template)
    if rule.audio.enabled and rule.audio.mode != "none":
        audio_path = audio.get_audio(rule.audio, context or {})
        if config.speakers.chromecast:
            tasks.append(trigger_chromecast(
                clients.chromecast, config.speakers.chromecast,
                audio_path, config.speakers.volume
            ))
        if config.speakers.airplay:
            tasks.append(trigger_airplay(
                clients.airplay, config.speakers.airplay,
                audio_path, config.speakers.volume
            ))

    # HomeKit doorbell notification
    if rule.homekit and config.homekit.enabled:
        tasks.append(trigger_homekit(clients.homekit))

    results = await asyncio.gather(*tasks, return_exceptions=True)
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
    F --> H[Create FastAPI app with lifespan]
    G --> H
    H --> I[Start uvicorn]
    I --> J[Lifespan startup: launch callback registration as background task]
    J --> K[Server accepts requests immediately]
```

1. Parse CLI args (`--config config.yaml`).
2. Load and validate config (defaults allow empty config).
3. Configure logging.
4. If HomeKit enabled: start HAP accessory driver in a background thread.
5. Create FastAPI app with `lifespan` context manager.
6. Start uvicorn — server is ready immediately.
7. Lifespan startup launches Nuki callback registration as `asyncio.create_task` (non-blocking, with infinite retry: 10s → 20s → 40s → 60s).

### Shutdown (Lifespan teardown)

Handled by the `lifespan` context manager's teardown phase:

```python
@asynccontextmanager
async def lifespan(app):
    # startup
    app.state.callback_id = None
    registration_task = asyncio.create_task(
        _register_callback_loop(config, clients, app)
    )
    yield
    # shutdown
    registration_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await registration_task
    await _deregister_callback(clients, app.state.callback_id)
    if clients.homekit is not None:
        clients.homekit.stop()
```

On shutdown: cancels the registration retry task (if still running), deregisters the callback from the Nuki Bridge, and stops HomeKit. If the Bridge is unreachable, deregistration is logged as a warning but does not block exit.

## Nuki Bridge Callback Payload

```json
{
    "nukiId": 12345,
    "deviceType": 2,
    "mode": 2,
    "state": 7,
    "stateName": "opening",
    "batteryCritical": false
}
```

Key fields:
- `deviceType`: 0=SmartLock, 2=Opener

**Opener states** (deviceType=2):
  - `1` = online (ring detected but door not opened → event: **ring**)
  - `3` = rto active
  - `5` = open
  - `7` = opening (door being opened → event: **ring_to_open**)

**Smart Lock states** (deviceType=0):
  - `1` = locked
  - `3` = unlocked → ignored (unlocking without opening must not notify — #60)
  - `5` = unlatched → event: **door_opened**
  - `7` = unlatched (lock’n’go)

### Event Classification Logic

```mermaid
flowchart TD
    A[Callback received] --> B{deviceType?}
    B -->|2 Opener| D{opener_id filter?}
    B -->|0 Smart Lock| J{lock_id filter?}
    B -->|Other| C[Ignore]
    D -->|Mismatch| C
    D -->|Match or no filter| E{state}
    E -->|7 opening| F[Event: ring_to_open]
    E -->|Ring detected| G[Event: ring]
    E -->|Other| C
    J -->|Mismatch| C
    J -->|Match or no filter| K{state}
    K -->|5 unlatched| L[Event: door_opened]
    K -->|Other| C
    F --> H[Dispatch ring_to_open rule]
    G --> I[Dispatch ring rule]
    L --> M[Dispatch door_opened rule]
```

Note: The exact state values will be confirmed during implementation against the Nuki Bridge HTTP API v1.13 documentation.

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
| GET | `/log?nukiId=&count=&token=` | Activity log (includes user name) |

### Chromecast Protocol

Via `pychromecast` — no direct HTTP. Library handles mDNS discovery, connection, and media casting.

### AirPlay 2 Protocol

Via `pyatv` — no direct HTTP. Library handles mDNS discovery, pairing, and audio streaming to HomePod and AirPlay 2 speakers.

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
        ER[event_router.py]
        CFG[config.py]
        DISC[discovery.py]
        HC[hue_client.py]
        CC[chromecast_client.py]
        AC[airplay_client.py]
        HKS[homekit_service.py]
    end

    UI -->|GET /api/config| WUI
    UI -->|PUT /api/config| WUI
    UI -->|GET /api/discover/*| WUI
    UI -->|POST /api/test/event/*| WUI
    WUI --> CFG
    WUI --> ER
    WUI --> DISC
    WUI --> HC
    WUI --> CC
    WUI --> AC
    WUI --> HKS
    CFG -->|read/write| YAML[(config.yaml)]
```

The frontend is a single `index.html` with embedded CSS/JS (no build step, no npm). Communicates with the backend via JSON API calls.

## CI/CD

- **GitHub Actions** (`.github/workflows/ci.yml`):
  - On push/PR: lint (flake8) + test (pytest).
- **Dependabot** (`.github/dependabot.yml`): auto-updates for pip, GitHub Actions, and Docker.
- **Local build**: Docker image is built on the Mini PC via `docker compose build`. No registry involved.

## Testing

All tests run via `make test` on the Mac. Real-device testing via `make runLocal`.

| Test file | Covers |
|---|---|
| `tests/test_config.py` | Config validation, load, save, defaults |
| `tests/test_server.py` | Callback endpoint (valid events, wrong device, unknown state) |
| `tests/test_event_router.py` | Event classification, person resolution (mock /log), rule dispatch |
| `tests/test_audio.py` | TTS generation, {name} template rendering, chime file resolution |
| `tests/test_web_ui.py` | Web UI API routes + localhost access control (403) |
| `tests/test_hue_client.py` | Hue API calls (mock httpx) |
| `tests/test_nuki_client.py` | Callback registration (mock httpx) |
| `tests/test_chromecast.py` | Chromecast audio playback (mock pychromecast) |
| `tests/test_airplay.py` | AirPlay audio playback (mock pyatv) |
| `tests/test_homekit.py` | HAP accessory lifecycle (mock HAP-python) |
| `tests/test_notifier.py` | Per-event rule channel dispatch, failure isolation |
| `tests/test_discovery.py` | Auto-discovery responses (mock zeroconf/pyatv) |
| `tests/test_lifecycle.py` | Startup registration, graceful shutdown deregistration, pause/resume |

## Docker

```dockerfile
FROM python:3.14.5-slim
# Poetry install → copy source → EXPOSE 8080 → ENTRYPOINT
```

### Production deployment (Mini PC)

```yaml
services:
  nukiblinker:
    build: .
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml       # read-write for web UI
      - ./homekit:/app/.homekit               # HomeKit pairing state
```

> **Note**: `network_mode: host` is required for mDNS-based speaker discovery and HomeKit. Port 8080 is exposed directly on the host (no port mapping needed). On WSL2, enable mirrored networking for full multicast support.

Deploy/update:

```sh
docker compose build && docker compose up -d
```

### Local testing (Mac)

```sh
make runLocal    # best for real-device testing (direct LAN + mDNS)
make build       # verify Docker image builds
```

## New Features (v0.3.0)

### Event Validation Service (`event_validator.py`)

Validates event timestamps before processing:

```python
class EventValidator:
    def __init__(self, max_delay_seconds: int = 60):
        self.max_delay_seconds = max_delay_seconds
    
    def validate_event(self, payload: dict) -> ValidationResult:
        """Check if event timestamp is within acceptable delay."""
        event_time = self._extract_timestamp(payload)
        now = datetime.now(timezone.utc)
        delay = (now - event_time).total_seconds()
        
        return ValidationResult(
            valid=delay <= self.max_delay_seconds,
            delay_seconds=delay,
            reason="Event too old" if delay > self.max_delay_seconds else None
        )
```

### Event Log Service (`event_log.py`)

Persistent event logging with web UI access:

```python
class EventLog:
    def __init__(self, max_entries: int = 1000, retention_days: int = 7):
        self.entries: list[EventLogEntry] = []
        self.max_entries = max_entries
        self.retention_days = retention_days
    
    def log_event(self, payload: dict, event_type: str, actions: list[str], validation_result: ValidationResult):
        """Add event to log with full context."""
        entry = EventLogEntry(
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            payload=payload,
            actions=actions,
            validation_result=validation_result
        )
        self.entries.append(entry)
        self._cleanup_old_entries()
    
    def get_recent_events(self, limit: int = 100) -> list[EventLogEntry]:
        """Return recent events for web UI."""
        return self.entries[-limit:]
```

### Night Mode Service (`night_mode.py`)

Manages time-based notification behavior:

```python
class NightMode:
    def __init__(self, start_time: str = "22:00", end_time: str = "07:00", brightness_factor: float = 0.3):
        self.start_time = start_time
        self.end_time = end_time
        self.brightness_factor = brightness_factor
    
    def is_night_time(self) -> bool:
        """Check if current time is within night mode hours."""
        now = datetime.now().time()
        start = datetime.strptime(self.start_time, "%H:%M").time()
        end = datetime.strptime(self.end_time, "%H:%M").time()
        
        if start <= end:
            return start <= now <= end
        else:  # Overnight (e.g., 22:00 to 07:00)
            return now >= start or now <= end
    
    def apply_night_mode(self, rule: EventRuleConfig) -> EventRuleConfig:
        """Return modified rule for night mode."""
        if not self.is_night_time():
            return rule
        
        night_rule = rule.copy(deep=True)
        night_rule.audio.enabled = False  # Disable audio
        
        # Reduce light brightness for custom blink
        if night_rule.blink.mode == "custom":
            night_rule.blink.custom.brightness = int(
                night_rule.blink.custom.brightness * self.brightness_factor
            )
        
        return night_rule
```

### Updated Config Models

Extended Pydantic models for new features:

```python
class EventValidationConfig(BaseModel):
    enabled: bool = True
    max_delay_seconds: int = 60  # Reject events older than 60 seconds

class NightModeConfig(BaseModel):
    enabled: bool = False
    start_time: str = "22:00"    # 10 PM
    end_time: str = "07:00"      # 7 AM
    brightness_factor: float = 0.3  # 30% of normal brightness
    grace_minutes: int = 5       # 5-minute buffer

class EventLogConfig(BaseModel):
    enabled: bool = True
    max_entries: int = 1000
    retention_days: int = 7
    persist_to_file: bool = True
    file_path: str = "logs/event_log.json"

class AppConfig(BaseModel):
    # ... existing fields ...
    event_validation: EventValidationConfig = EventValidationConfig()
    night_mode: NightModeConfig = NightModeConfig()
    event_log: EventLogConfig = EventLogConfig()
```

### Updated Web UI API Routes

New endpoints in `web_ui.py`:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/events/log` | Get recent event log entries |
| GET | `/api/events/export` | Download event log as CSV |
| POST | `/api/events/clear` | Clear event log |
| PUT | `/api/config/event-validation` | Update validation settings |
| PUT | `/api/config/night-mode` | Update night mode settings |
| PUT | `/api/config/event-log` | Update event log settings |

### Updated Event Flow

```mermaid
sequenceDiagram
    participant NB as Nuki Bridge
    participant NK as NukiBlinker
    participant EV as EventValidator
    participant EL as EventLog
    participant NM as NightMode
    participant ER as EventRouter
    participant N as Notifier

    NB->>NK: HTTP POST /nuki/callback
    NK->>EV: validate_event(payload)
    EV-->>NK: ValidationResult
    alt Event invalid (too old)
        NK->>EL: log_event(validation_result=invalid)
        NK-->>NB: 200 OK (no notifications)
    else Event valid
        NK->>EL: log_event(validation_result=valid)
        NK->>NM: is_night_time()?
        NM-->>NK: boolean
        NK->>ER: classify_and_dispatch(payload, night_mode_rule)
        ER->>N: notify()
        N-->>ER: results
        ER-->>NK: actions_taken
        NK->>EL: log_event(actions=actions_taken)
        NK-->>NB: 200 OK
    end
```

## Logging

- Structured logging via Python `logging` module.
- Console output (INFO level by default).
- Rotating file log (`logs/nukiblinker.log`), configurable retention.
- Event log service: separate structured log for event processing (JSON format).
- Key events logged: startup, callback received, event classified (ring / ring_to_open), rule dispatched, channel triggered, channel failure, config saved.
- Event validation warnings when events are rejected due to age.
- Night mode activation/deactivation logs.
