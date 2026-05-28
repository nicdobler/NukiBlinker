# NukiBlinker

NukiBlinker blinks your Philips Hue lights when someone rings the doorbell on your Nuki Opener. It runs as a lightweight service on your local network, listening for Nuki Bridge callbacks and triggering Hue light alerts.

## How It Works

1. NukiBlinker starts and registers a webhook callback on your Nuki Bridge.
2. Visitor presses the doorbell → Nuki Opener detects a ring → Nuki Bridge sends a callback.
3. NukiBlinker triggers your configured Hue lights to blink.
4. Lights return to their previous state automatically.

## Blink Modes

- **Alert** (default) — Uses Hue's built-in 15-second blink. Zero-config, reliable.
- **Custom** — Configurable color, flash count, and interval. Lights are saved/restored.

## Prerequisites

- **Nuki Opener** connected to a **Nuki Bridge** on your LAN
- **Philips Hue Bridge** on the same LAN
- **Docker** (recommended), or **Python >= 3.11** + [Poetry](https://python-poetry.org/)

## Configuration

Copy `config.example.yaml` to `config.yaml` and fill in your bridge IPs and API keys:

```sh
cp config.example.yaml config.yaml
```

See `config.example.yaml` for all available options.

### Getting API Keys

- **Nuki Bridge**: Enable the HTTP API in the Nuki app → Settings → Manage Bridge → Enable API. Note the token.
- **Hue Bridge**: Press the link button on the Hue Bridge, then `POST` to `http://<bridge-ip>/api` with `{"devicetype":"nukiblinker"}`. Use the returned `username` as `api_key`.

## Deployment (Mini PC)

The Docker image is built automatically by GitHub Actions on merge to `main` and pushed to GHCR.

### First-time setup

1. Create a directory on the Mini PC (e.g. `~/nukiblinker/`).
2. Copy `config.example.yaml` to `config.yaml` and fill in your bridge credentials.
3. Copy `docker-compose.yml` to the same directory.
4. Run:

```sh
docker compose up -d
```

### Updating

```sh
docker compose pull && docker compose up -d
```

### Local development (Mac only)

```sh
pip install poetry
poetry install
make test
make lint
make runLocal
```

## Development

| Command | Description | Where |
|---|---|---|
| `make test` | Run unit tests with pytest | Mac / CI |
| `make lint` | Run flake8 (line-length 120) | Mac / CI |
| `make format` | Show Black diff | Mac |
| `make install` | Install/update dependencies | Mac |
| `make build` | Build Docker image locally | Mac (optional) |

> **Note**: No testing or building on the work laptop. Code only.

### Tech Stack

- **Python 3.14** (Docker base `python:3.14.5-slim`)
- **FastAPI** + **uvicorn** (async HTTP server)
- **httpx** (async HTTP client for bridge APIs)
- **pydantic** (config validation)
- **Black** (formatter, line-length 120) · **flake8** (linter) · **pytest**
