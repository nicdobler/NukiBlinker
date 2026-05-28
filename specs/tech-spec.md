# Tech Spec — NukiBlinker

## Architecture Overview

```
nukiblinker/
├── __main__.py           # Entry point — loads config, starts server
├── config.py             # YAML config loading + Pydantic validation
├── server.py             # FastAPI app — receives Nuki Bridge callbacks
├── nuki_client.py        # Nuki Bridge HTTP API client (callback registration)
├── hue_client.py         # Philips Hue Bridge API client (light control)
├── blinker.py            # Orchestrates blink sequences (alert + custom)
└── logging_config.py     # Structured logging setup
```

## Runtime

- **Python >= 3.11** (Docker image: `python:3.14.5-slim`)
- **Poetry** for dependency management
- **Docker** for deployment on Mini PC (WSL2), `--network host` for LAN access
- Key dependencies: `fastapi`, `uvicorn`, `httpx`, `pyyaml`, `pydantic`

## Execution Environment

- **Target**: Mini PC running Windows with WSL2/Docker.
- **Network**: `--network host` mode so the container shares the host's LAN IP, making it reachable by the Nuki Bridge for callbacks.
- **Persistence**: Stateless — no database. Config is mounted as a read-only volume.

### Development Environments

| Environment | Role |
|---|---|
| Work laptop (Windows) | Code only. No testing, no Poetry, no Docker. |
| Personal Mac | Test & validate (`make test`, `make lint`). |
| GitHub Actions | CI/CD: lint → test → build Docker → push to GHCR. |
| Mini PC (Windows + WSL2) | Production: `docker compose pull && up -d`. |

## Component Design

### Config (`config.py`)

Pydantic models validate the YAML config at startup. Fail fast with clear errors.

```python
class NukiConfig(BaseModel):
    bridge_ip: str
    bridge_port: int = 8080
    api_token: str
    opener_id: int | None = None  # optional filter

class HueConfig(BaseModel):
    bridge_ip: str
    api_key: str
    lights: list[int] = []        # light IDs
    groups: list[int] = []        # group IDs

class CustomBlinkConfig(BaseModel):
    hue: int = 0                  # 0-65535
    saturation: int = 254         # 0-254
    brightness: int = 254         # 1-254
    flashes: int = 3
    interval_ms: int = 500

class BlinkConfig(BaseModel):
    mode: str = "alert"           # "alert" or "custom"
    custom: CustomBlinkConfig = CustomBlinkConfig()

class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080

class AppConfig(BaseModel):
    nuki: NukiConfig
    hue: HueConfig
    blink: BlinkConfig = BlinkConfig()
    server: ServerConfig = ServerConfig()
```

### Server (`server.py`)

FastAPI app with a single POST endpoint:

- **`POST /nuki/callback`** — Receives Nuki Bridge callback payloads.
  - Validates `deviceType == 2` (Opener) and `state == 7` (ring detected).
  - Optionally filters by `nukiId` if `opener_id` is configured.
  - On valid ring: triggers blinker asynchronously.
  - Returns 200 immediately (Nuki Bridge expects fast response).

- **`GET /health`** — Health check endpoint.

### Nuki Client (`nuki_client.py`)

Manages the Nuki Bridge HTTP API:

- **`register_callback(callback_url)`** — Calls `GET /callback/add?url=<url>&token=<token>`.
  - First lists existing callbacks via `GET /callback/list` to avoid duplicates.
  - If the callback URL is already registered, skips re-registration.
- **`list_callbacks()`** — Returns current registered callbacks.
- **`remove_callback(callback_id)`** — Removes a callback by ID.

### Hue Client (`hue_client.py`)

Manages the Philips Hue Bridge API:

- **`trigger_alert(light_ids, group_ids)`** — Sends `{"alert": "lselect"}` to each target.
- **`get_light_state(light_id)`** — Reads current state (on/off, bri, hue, sat, ct).
- **`set_light_state(light_id, state)`** — Sets light to a specific state.
- **`trigger_custom_blink(light_ids, config)`** — Custom blink sequence:
  1. Save current state of each light.
  2. Loop `config.flashes` times: set color → wait → turn off → wait.
  3. Restore previous state.

Uses `httpx.AsyncClient` for non-blocking HTTP calls.

### Blinker (`blinker.py`)

Orchestrates the blink sequence:

```python
async def blink(hue_client, config):
    if config.blink.mode == "alert":
        await hue_client.trigger_alert(config.hue.lights, config.hue.groups)
    elif config.blink.mode == "custom":
        await hue_client.trigger_custom_blink(
            config.hue.lights, config.blink.custom
        )
```

### Entry Point (`__main__.py`)

1. Parse CLI args (`--config config.yaml`).
2. Load and validate config.
3. Configure logging.
4. Register callback on Nuki Bridge (idempotent).
5. Start FastAPI/uvicorn server.

## Event Flow

```
Doorbell press
    → Nuki Opener detects ring (state=7)
    → Nuki Bridge sends HTTP POST to NukiBlinker callback URL
    → server.py validates payload (deviceType=2, state=7)
    → blinker.py triggers HueClient
    → HueClient sends PUT to Hue Bridge API
    → Lights blink
```

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

## Hue API Endpoints Used

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/{key}/lights/{id}` | Read light state |
| PUT | `/api/{key}/lights/{id}/state` | Set light state |
| PUT | `/api/{key}/groups/{id}/action` | Set group action |

## CI/CD

- **GitHub Actions** (`.github/workflows/ci.yml`):
  - On push/PR: lint (flake8) + test (pytest).
  - On merge to `main`: build Docker image + push to `ghcr.io/<owner>/nukiblinker:latest` (also tagged by commit SHA).
- **Dependabot** (`.github/dependabot.yml`): auto-updates for pip, GitHub Actions, and Docker.
- **GHCR**: GitHub Container Registry. Image is public. No secrets needed on the Mini PC to pull.

## Testing

- **pytest** with `pytest-asyncio` for async code.
- `tests/test_config.py` — Config validation (valid, missing fields, invalid values).
- `tests/test_server.py` — Callback endpoint (valid ring, wrong device type, wrong state, missing fields).
- `tests/test_hue_client.py` — Hue API calls (mock httpx).
- `tests/test_nuki_client.py` — Callback registration (mock httpx).
- `tests/test_blinker.py` — Blink orchestration (mock HueClient).

## Docker

```dockerfile
FROM python:3.14.5-slim
# Poetry install → copy source → ENTRYPOINT runs nukiblinker module
```

### Production deployment (Mini PC)

`docker-compose.yml` in the project root:

```yaml
services:
  nukiblinker:
    image: ghcr.io/<owner>/nukiblinker:latest
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml:ro
```

Deploy/update:

```sh
docker compose pull && docker compose up -d
```

### Local build (Mac, optional)

```sh
make build
docker run --network host -v ./config.yaml:/app/config.yaml:ro nukiblinker
```

## Logging

- Structured logging via Python `logging` module.
- Console output (INFO level by default).
- Rotating file log (`logs/nukiblinker.log`), configurable retention.
- Key events logged: startup, callback received, ring detected, blink triggered, errors.
