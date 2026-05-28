# Product Spec — NukiBlinker

## Vision

A lightweight, always-on service that makes Philips Hue lights blink when someone rings the doorbell on a Nuki Opener, providing a visible notification throughout the house.

## Problem

The Nuki Opener handles intercom/doorbell events but has no built-in way to trigger visual alerts on other smart home devices. In a large house or when wearing headphones, the intercom ring can be missed. Blinking the Hue lights provides an unmissable visual cue.

## Users

Individual homeowner running a Nuki Opener + Philips Hue Bridge on the same local network.

## How It Works (User Perspective)

1. User configures NukiBlinker with Nuki Bridge and Hue Bridge credentials.
2. NukiBlinker starts and registers a webhook callback on the Nuki Bridge.
3. A visitor presses the doorbell → Nuki Opener detects a ring event.
4. Nuki Bridge sends an HTTP callback to NukiBlinker.
5. NukiBlinker triggers the configured Hue lights to blink.
6. Lights return to their previous state after the blink sequence.

## Devices & APIs

| Device | Role | API |
|---|---|---|
| Nuki Bridge | Pushes ring events via HTTP callback | [Nuki Bridge HTTP API](https://developer.nuki.io/page/nuki-bridge-http-api-1-13/4) |
| Nuki Opener | Detects doorbell ring (deviceType=2, state=7) | Via Nuki Bridge |
| Philips Hue Bridge | Controls lights | [Hue CLIP API v2](https://developers.meethue.com/develop/hue-api-v2/) / v1 REST |

## Blink Modes

### 1. Built-in Alert (default)
- Uses Hue's native `"alert": "lselect"` — 15-second blink cycle.
- Zero configuration beyond selecting which lights/groups.
- Lights return to previous state automatically.

### 2. Custom Pattern
- Configurable via `config.yaml`.
- Parameters: color (HSB), number of flashes, interval between flashes.
- NukiBlinker saves light state before blinking, restores after.

Mode is selected per deployment in `config.yaml`. Default: built-in alert.

## Configuration

All settings live in `config.yaml` (not committed to git). An example template `config.example.yaml` is provided.

Key settings:
- **Nuki Bridge**: IP, port, API token, optional Opener ID filter.
- **Hue Bridge**: IP, API key, list of light IDs and/or group IDs to blink.
- **Blink mode**: `alert` or `custom` (with color, flashes, interval).
- **Server**: host and port for the callback listener.
- **Logging**: level, file path.

## Acceptance Criteria

1. **Ring detection** — A doorbell ring on the Nuki Opener triggers the callback within 2 seconds.
2. **Light blink** — Configured Hue lights blink visibly within 1 second of receiving the callback.
3. **State restore** — After a custom blink sequence, lights return to their exact previous state (on/off, brightness, color).
4. **Resilience** — If a Hue light is unreachable, NukiBlinker logs a warning but does not crash.
5. **Idempotent startup** — Multiple restarts do not create duplicate callbacks on the Nuki Bridge.
6. **Config validation** — Invalid config is rejected at startup with a clear error message.
7. **Tests** — Unit tests cover the event pipeline, Hue client, and config validation.
8. **Lint** — `make lint` passes with zero errors.

## Non-Goals (Current)

- No GUI or web dashboard.
- No integration with Nuki Cloud API (local bridge only).
- No support for other smart home platforms (HomeKit, Alexa, etc.).
- No multi-bridge support (single Nuki Bridge + single Hue Bridge).
- No "ring to open" automation — this is notification only.

## Future Considerations

- Support for multiple Hue Bridges or light groups with different patterns.
- Cooldown period to prevent rapid re-triggering.
- Integration with other Nuki events (lock, unlock, door open).
- Push notification fallback (e.g., Pushover, Telegram) when not home.
- Web dashboard for status and configuration.
