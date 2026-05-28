# Product Spec — NukiBlinker

## Vision

A lightweight, always-on service that reacts to Nuki Opener doorbell events — blinking Philips Hue lights, announcing on Google Nest and HomePod speakers, and sending Apple HomeKit doorbell alerts. Different events trigger different actions.

## Problem

The Nuki Opener handles intercom/doorbell events but has no built-in way to trigger visual or audio alerts on other smart home devices. In a large house or when wearing headphones, the intercom ring can be missed. NukiBlinker bridges this gap with configurable reactions: different blink patterns, voice announcements, and push notifications depending on the event type.

## Users

Individual homeowner running a Nuki Opener and one or more of: Philips Hue Bridge, Google Nest speakers, Apple HomePod, Apple HomeKit devices — all on the same local network.

## How It Works (User Perspective)

1. User configures NukiBlinker via the web UI (bridges, speakers, event rules).
2. NukiBlinker starts and registers a webhook callback on the Nuki Bridge.
3. A visitor presses the doorbell → Nuki Opener detects the event.
4. Nuki Bridge sends an HTTP callback to NukiBlinker.
5. NukiBlinker identifies the event type (ring vs ring-to-open) and fires the matching rule:
   - **Ring (unknown visitor)**: Hue lights blink with a warning pattern.
   - **Ring to open (authorized person)**: Different blink pattern + voice announcement ("Nico ha llegado a casa") on HomePod / Google Nest.
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
| Nuki Opener | Detects doorbell ring (deviceType=2) | Via Nuki Bridge |
| Philips Hue Bridge | Controls lights | [Hue CLIP API v2](https://developers.meethue.com/develop/hue-api-v2/) / v1 REST |
| Google Nest / Home | Voice announcements | Chromecast protocol (`pychromecast`) + TTS (`gTTS`) |
| Apple HomePod | Voice announcements | AirPlay 2 (`pyatv`) + TTS (`gTTS`) |
| Apple HomeKit | Doorbell notifications on iPhone/iPad/Watch/Mac | HomeKit Accessory Protocol (`HAP-python`) |

## Event Types

The Nuki Opener produces different events. NukiBlinker maps each to a configurable set of actions via **event rules**.

| Event | Nuki state | Meaning | Default actions |
|---|---|---|---|
| **Ring (no open)** | Ring detected, door stays closed | Unknown visitor rang the doorbell | Hue lights blink (warning pattern) |
| **Ring to open** | Ring detected, door opened (RTO active) | Authorized person arrived | Different blink + voice announcement |

Each event rule configures:
- Which **notification channels** to fire (checkboxes).
- Which **blink pattern** to use (alert, custom, or none).
- Which **announcement message** to speak (per-event text).

Example configuration:

| | Ring (no open) | Ring to open |
|---|---|---|
| Hue Lights | ✅ Red flash, 5x | ✅ Green flash, 2x |
| Voice Announcement | ❌ | ✅ "Nico ha llegado a casa" |
| HomeKit Notification | ✅ | ✅ |

## Blink Modes

### 1. Built-in Alert (default)
- Uses Hue's native `"alert": "lselect"` — 15-second blink cycle.
- Zero configuration beyond selecting which lights/groups.
- Lights return to previous state automatically.

### 2. Custom Pattern
- Parameters: color (HSB), number of flashes, interval between flashes.
- NukiBlinker saves light state before blinking, restores after.
- Each event rule can have its own custom pattern (e.g., red for unknown ring, green for RTO).

## Notification Channels

All enabled channels fire in parallel. Each event rule selects which channels to trigger.

| Channel | Type | What happens | Required hardware |
|---|---|---|---|
| **Hue Lights** | Visual | Lights blink (per-event pattern) | Hue Bridge |
| **Voice Announcements** | Audio | TTS message on speakers | Google Nest (Chromecast) and/or HomePod (AirPlay) |
| **Apple HomeKit** | Push notification | Native doorbell alert on all Apple devices | iPhone/iPad/Watch/Mac |

### Voice Announcements

TTS announcements on **Google Nest** and/or **Apple HomePod** speakers.

- **Google Nest / Home**: Uses Chromecast protocol via `pychromecast`. Speakers auto-discovered on LAN.
- **Apple HomePod**: Uses AirPlay 2 via `pyatv`. Speakers auto-discovered on LAN.
- TTS audio generated via `gTTS` (Google Text-to-Speech) — requires internet.
- Announcement message is configurable **per event rule** (e.g., "Someone is at the door" vs "Nico ha llegado a casa").
- Volume can be set independently of the speaker's current volume.
- Both speaker types can be active simultaneously.

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
   - IP and port (auto-discovered if possible; manual fallback).
   - API token.
   - Opener selection (if multiple Openers are paired, pick which one triggers events).

2. **Hue Bridge**
   - IP (auto-discovered if possible; manual fallback).
   - API key (with a "Press bridge button and pair" flow if no key exists).
   - Light/group picker — shows discovered lights and groups with checkboxes.

3. **Speakers**
   - Speaker picker — shows auto-discovered Google Nest (Chromecast) and HomePod (AirPlay) devices with checkboxes.
   - Volume override (slider).
   - "Test announce" button.

4. **Apple HomeKit**
   - Enable/disable HomeKit doorbell.
   - Pairing status and HomeKit setup code / QR code for initial pairing.
   - "Test notification" button.

5. **Event Rules**
   - One card per event type (Ring, Ring to open).
   - Each card configures:
     - Hue: enable + blink pattern (alert/custom with color, flashes, interval).
     - Voice: enable + announcement message text.
     - HomeKit: enable/disable.
   - "Test" button per event rule (fires all enabled channels for that rule).

6. **Status**
   - Connection status for all bridges and speakers (reachable / unreachable).
   - Last event timestamp and type.
   - Service uptime.
   - Pause / Resume button.

**Auto-discovery**:
- Nuki Bridge: discovered via Nuki Cloud discovery endpoint (`https://api.nuki.io/discover/bridges`) or local UDP broadcast.
- Hue Bridge: discovered via mDNS (`_hue._tcp.local`) or Philips discovery endpoint (`https://discovery.meethue.com`).
- Google Nest / Chromecast speakers: discovered via `pychromecast` (mDNS/zeroconf).
- Apple HomePod / AirPlay speakers: discovered via `pyatv` (mDNS/zeroconf).
- If auto-discovery finds a device, the IP / name is pre-filled. User can always override manually.

### Config file (`config.yaml`)

Key settings:
- **Nuki Bridge**: IP, port, API token, optional Opener ID filter.
- **Hue Bridge**: IP, API key, list of light IDs and/or group IDs to blink.
- **Speakers**: list of speaker names/IPs (Chromecast + AirPlay), volume.
- **HomeKit**: enabled flag, pairing state/code.
- **Event rules**: per-event config (channels enabled, blink pattern, announcement message).
- **Server**: host and port for the callback listener.
- **Logging**: level, file path.

## Acceptance Criteria

1. **Event detection** — Doorbell events on the Nuki Opener trigger the callback within 2 seconds.
2. **Event classification** — Ring (no open) and Ring to open are correctly distinguished and routed to the matching rule.
3. **Light blink** — Configured Hue lights blink with the per-event pattern within 1 second of receiving the callback.
4. **State restore** — After a custom blink sequence, lights return to their exact previous state (on/off, brightness, color).
5. **Voice announcements** — TTS plays on selected Google Nest and/or HomePod speakers within 2 seconds.
6. **HomeKit** — Doorbell notification appears on all paired Apple devices within 2 seconds.
7. **Per-event rules** — Each event type has independently configurable channels, blink pattern, and announcement message.
8. **Resilience** — If a channel target is unreachable, NukiBlinker logs a warning but does not crash.
9. **Channel independence** — Each notification channel works independently; a failure in one does not block others.
10. **Idempotent startup** — Multiple restarts do not create duplicate callbacks on the Nuki Bridge.
11. **Config validation** — Invalid config is rejected at startup with a clear error message.
12. **Web UI** — Config page is accessible only from `localhost`. All settings are editable and persist to `config.yaml`.
13. **Auto-discovery** — Nuki Bridge, Hue Bridge, Chromecast speakers, and AirPlay speakers are auto-discovered when available.
14. **Test buttons** — Per-event "Test" button fires all enabled channels for that rule without a real doorbell event.
15. **Graceful shutdown** — `docker compose down` deregisters the Nuki callback before exiting.
16. **Pause/Resume** — Web UI pause button deregisters callback without stopping the service; resume re-registers it.
17. **Tests** — Unit tests cover event classification, all notification channels, event rules, config validation, web UI access control, and shutdown hook.
18. **Lint** — `make lint` passes with zero errors.

## Non-Goals (Current)

- No integration with Nuki Cloud API (local bridge only, except for bridge discovery).
- No Alexa support (no public local API for announcements).
- No multi-bridge support (single Nuki Bridge + single Hue Bridge).
- No door-opening automation — NukiBlinker is notification only, it never opens the door.
- No visitor identification — the system knows "ring" vs "ring to open", not who rang.
- No remote access to the web UI — localhost only.

## Future Considerations

- Support for multiple Hue Bridges or light groups with different patterns.
- Cooldown period to prevent rapid re-triggering.
- Additional Nuki event types (lock, unlock, door open) as triggers.
- Push notification fallback (e.g., Pushover, Telegram) when not home.
- Optional authentication for the web UI (to allow LAN-wide access).
- Per-person announcements if combined with a camera/face recognition system.
