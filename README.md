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
- **Web UI**: localhost-only config page at `http://localhost:8080/`
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

## Configuration

See `config.example.yaml` for all options. Key sections:

- **nuki** — Bridge IP, port, API token, optional opener/lock ID filters
- **hue** — Bridge IP, API key, light/group IDs
- **speakers** — Chromecast and AirPlay speaker names, volume
- **homekit** — Enable/disable, setup code
- **events** — Per-event rules (ring, ring_to_open, door_opened)
- **server** — Host and port

### Getting API Keys

- **Nuki Bridge**: Nuki app → Settings → Manage Bridge → Enable API. Note the token.
- **Hue Bridge**: Press link button, then `POST http://<bridge-ip>/api {"devicetype":"nukiblinker"}`.

## Deployment (Mini PC)

```sh
docker compose pull && docker compose up -d
```

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
