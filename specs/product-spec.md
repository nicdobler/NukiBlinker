# Product Spec — NukiBlinker

## Vision

A lightweight, always-on service that notifies you when someone rings the doorbell on a Nuki Opener — by blinking Philips Hue lights, announcing on Google Home/Nest speakers, and sending Apple HomeKit doorbell alerts.

## Problem

The Nuki Opener handles intercom/doorbell events but has no built-in way to trigger visual or audio alerts on other smart home devices. In a large house or when wearing headphones, the intercom ring can be missed. NukiBlinker bridges this gap by triggering Hue lights, Google Home announcements, and Apple HomeKit doorbell notifications.

## Users

Individual homeowner running a Nuki Opener and one or more of: Philips Hue Bridge, Google Home/Nest speakers, Apple HomeKit devices — all on the same local network.

## How It Works (User Perspective)

1. User configures NukiBlinker via the web UI (bridges, speakers, notification channels).
2. NukiBlinker starts and registers a webhook callback on the Nuki Bridge.
3. A visitor presses the doorbell → Nuki Opener detects a ring event.
4. Nuki Bridge sends an HTTP callback to NukiBlinker.
5. NukiBlinker triggers all enabled notification channels in parallel:
   - Hue lights blink.
   - Google Home/Nest speakers announce "Someone is at the door."
   - Apple HomeKit devices receive a doorbell notification.
6. Lights return to their previous state after the blink sequence.

## Lifecycle

| Action | How | What happens |
|---|---|---|
| **Start** | `docker compose up -d` or `make runLocal` | Registers callback on Nuki Bridge, starts HomeKit accessory, begins listening. |
| **Stop** | `docker compose down` or Ctrl+C | Deregisters callback from Nuki Bridge, stops HomeKit, clean exit. |
| **Pause** | Web UI "Pause" button | Deregisters Nuki callback but keeps the service running. Web UI stays accessible. |
| **Resume** | Web UI "Resume" button | Re-registers the Nuki callback. Notifications resume. |

### Graceful shutdown

On `SIGTERM` or `SIGINT` (sent by Docker on stop), NukiBlinker:
1. Deregisters the callback from the Nuki Bridge.
2. Stops the HomeKit accessory driver.
3. Exits cleanly.

The Nuki Bridge does not retry or error when a callback URL is unreachable — it silently skips. So even on an ungraceful crash, there is no user-visible impact. On next startup, the stale callback is detected and reused (idempotent).

## Devices & APIs

| Device | Role | API / Protocol |
|---|---|---|
| Nuki Bridge | Pushes ring events via HTTP callback | [Nuki Bridge HTTP API](https://developer.nuki.io/page/nuki-bridge-http-api-1-13/4) |
| Nuki Opener | Detects doorbell ring (deviceType=2, state=7) | Via Nuki Bridge |
| Philips Hue Bridge | Controls lights | [Hue CLIP API v2](https://developers.meethue.com/develop/hue-api-v2/) / v1 REST |
| Google Home / Nest | Voice announcements | Chromecast protocol (`pychromecast`) + TTS (`gTTS`) |
| Apple HomeKit | Doorbell notifications on iPhone/iPad/Watch/HomePod | HomeKit Accessory Protocol (`HAP-python`) |

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

## Notification Channels

Each channel is independently enabled/disabled via the web UI. All enabled channels fire in parallel on a ring event.

| Channel | Type | What happens | Required hardware |
|---|---|---|---|
| **Hue Lights** | Visual | Lights blink (alert or custom pattern) | Hue Bridge |
| **Google Home** | Audio | TTS announcement: "Someone is at the door" | Any Chromecast-compatible speaker |
| **Apple HomeKit** | Notification | Native doorbell alert on all Apple devices | iPhone/iPad/Watch (no extra hardware) |

### Google Home Announcements
- Uses the Chromecast protocol to cast TTS audio to selected speakers.
- Speakers are auto-discovered on the LAN via `pychromecast`.
- TTS generated locally via `gTTS` (Google Text-to-Speech) — requires internet.
- Announcement message is configurable (default: "Someone is at the door").
- Volume can be set independently of the speaker's current volume.

### Apple HomeKit Doorbell
- NukiBlinker exposes a virtual HomeKit doorbell accessory via `HAP-python`.
- On first setup, user scans the HomeKit pairing code from the web UI (or enters the setup code manually in the Home app).
- When a ring is detected, all paired Apple devices receive a native doorbell notification.
- No HomePod required — works with iPhone, iPad, Apple Watch, and Mac.

## Configuration

Settings are managed via a **web configuration page** served by NukiBlinker itself. The config is persisted to `config.yaml` on disk.

An example template `config.example.yaml` is provided for initial bootstrap (before the web UI is available).

### Web Configuration UI

A simple, single-page web interface for configuring NukiBlinker.

**Access control**: The web UI is only accessible from the Mini PC itself (`127.0.0.1` / `localhost`). Requests from any other IP are rejected with `403 Forbidden`.

**Sections**:

1. **Nuki Bridge**
   - IP and port (auto-discovered via mDNS/SSDP if possible; manual fallback).
   - API token.
   - Opener selection (if multiple Openers are paired, pick which one triggers blinks).

2. **Hue Bridge**
   - IP (auto-discovered via mDNS/SSDP if possible; manual fallback).
   - API key (with a "Press bridge button and pair" flow if no key exists).
   - Light/group picker — shows discovered lights and groups with checkboxes.

3. **Blink Mode**
   - Toggle between `alert` (built-in) and `custom`.
   - Custom parameters: color picker (HSB), number of flashes, interval.
   - "Test blink" button to preview the current settings.

4. **Google Home**
   - Enable/disable announcements.
   - Speaker picker — shows auto-discovered Chromecast devices with checkboxes.
   - Announcement message (editable text field).
   - Volume override (slider).
   - "Test announce" button.

5. **Apple HomeKit**
   - Enable/disable HomeKit doorbell.
   - Pairing status and HomeKit setup code / QR code for initial pairing.
   - "Test notification" button.

6. **Status**
   - Connection status for all bridges and speakers (reachable / unreachable).
   - Last ring event timestamp.
   - Service uptime.

**Auto-discovery**:
- Nuki Bridge: discovered via Nuki Cloud discovery endpoint (`https://api.nuki.io/discover/bridges`) or local UDP broadcast.
- Hue Bridge: discovered via mDNS (`_hue._tcp.local`) or Philips discovery endpoint (`https://discovery.meethue.com`).
- Google Home / Chromecast speakers: discovered via `pychromecast` (mDNS/zeroconf).
- If auto-discovery finds a device, the IP / name is pre-filled. User can always override manually.

### Config file (`config.yaml`)

Key settings:
- **Nuki Bridge**: IP, port, API token, optional Opener ID filter.
- **Hue Bridge**: IP, API key, list of light IDs and/or group IDs to blink.
- **Blink mode**: `alert` or `custom` (with color, flashes, interval).
- **Google Home**: enabled flag, list of speaker names/IPs, announcement message, volume.
- **HomeKit**: enabled flag, pairing state/code.
- **Server**: host and port for the callback listener.
- **Logging**: level, file path.

## Acceptance Criteria

1. **Ring detection** — A doorbell ring on the Nuki Opener triggers the callback within 2 seconds.
2. **Light blink** — Configured Hue lights blink visibly within 1 second of receiving the callback.
3. **State restore** — After a custom blink sequence, lights return to their exact previous state (on/off, brightness, color).
4. **Resilience** — If a Hue light is unreachable, NukiBlinker logs a warning but does not crash.
5. **Idempotent startup** — Multiple restarts do not create duplicate callbacks on the Nuki Bridge.
6. **Config validation** — Invalid config is rejected at startup with a clear error message.
7. **Web UI** — Config page is accessible only from `localhost`. All settings are editable and persist to `config.yaml`.
8. **Auto-discovery** — Nuki Bridge, Hue Bridge, and Chromecast speakers are auto-discovered when available; manual entry always works.
9. **Test buttons** — "Test blink", "Test announce", and "Test notification" buttons work without a real doorbell ring.
10. **Google Home** — TTS announcement plays on selected speakers within 2 seconds of a ring event.
11. **HomeKit** — Doorbell notification appears on all paired Apple devices within 2 seconds of a ring event.
12. **Channel independence** — Each notification channel works independently; a failure in one does not block others.
13. **Graceful shutdown** — `docker compose down` deregisters the Nuki callback before exiting. No stale callbacks left.
14. **Pause/Resume** — Web UI pause button deregisters callback without stopping the service; resume re-registers it.
15. **Tests** — Unit tests cover the event pipeline, all notification channels, config validation, web UI access control, and shutdown hook.
16. **Lint** — `make lint` passes with zero errors.

## Non-Goals (Current)

- No integration with Nuki Cloud API (local bridge only, except for bridge discovery).
- No Alexa support (no public local API for announcements).
- No multi-bridge support (single Nuki Bridge + single Hue Bridge).
- No "ring to open" automation — this is notification only.
- No remote access to the web UI — localhost only.

## Future Considerations

- Support for multiple Hue Bridges or light groups with different patterns.
- Cooldown period to prevent rapid re-triggering.
- Integration with other Nuki events (lock, unlock, door open).
- Push notification fallback (e.g., Pushover, Telegram) when not home.
- Optional authentication for the web UI (to allow LAN-wide access).
