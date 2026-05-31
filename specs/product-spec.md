# Product Spec — NukiBlinker

## Vision

A lightweight, always-on service that reacts to Nuki smart lock events — blinking Philips Hue lights, playing chimes and announcements on Google Nest and HomePod speakers, and sending Apple HomeKit doorbell alerts. Different events trigger different actions.

## Problem

Nuki devices (Opener + Smart Lock) handle doorbell and door events but have no built-in way to trigger visual or audio alerts on other smart home devices. In a large house or when wearing headphones, the intercom ring or door opening can be missed. NukiBlinker bridges this gap with configurable reactions: different blink patterns, chimes, voice announcements, and push notifications depending on the event type.

## Users

Individual homeowner running a Nuki Opener and/or Nuki Smart Lock, plus one or more of: Philips Hue Bridge, Google Nest speakers, Apple HomePod, Apple HomeKit devices — all on the same local network.

## How It Works (User Perspective)

1. User configures NukiBlinker via the web UI (bridges, speakers, event rules).
2. NukiBlinker starts and registers a webhook callback on the Nuki Bridge.
3. An event occurs on a Nuki device (doorbell ring, door opened, etc.).
4. Nuki Bridge sends an HTTP callback to NukiBlinker.
5. NukiBlinker identifies the event type and fires the matching rule:
   - **Ring (unknown visitor)**: Hue lights blink with a warning pattern.
   - **Ring to open (authorized person)**: Different blink + personalized announcement ("{name} llegó a casa").
   - **Door opened (Smart Lock)**: Chime sound on speakers.
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
| Nuki Bridge | Pushes events via HTTP callback | [Nuki Bridge HTTP API](https://developer.nuki.io/page/nuki-bridge-http-api-1-13/4) |
| Nuki Opener | Detects doorbell ring (deviceType=2) | Via Nuki Bridge |
| Nuki Smart Lock | Detects door open/lock/unlock (deviceType=0) | Via Nuki Bridge |
| Philips Hue Bridge | Controls lights | [Hue CLIP API v2](https://developers.meethue.com/develop/hue-api-v2/) / v1 REST |
| Google Nest / Home | Chimes and voice announcements | Chromecast protocol (`pychromecast`) + TTS (`gTTS`) |
| Apple HomePod | Chimes and voice announcements | AirPlay 2 (`pyatv`) + TTS (`gTTS`) |
| Apple HomeKit | Doorbell notifications on iPhone/iPad/Watch/Mac | HomeKit Accessory Protocol (`HAP-python`) |

## Event Types

Nuki devices produce different events. NukiBlinker maps each to a configurable set of actions via **event rules**.

| Event | Nuki device | Meaning | Default actions |
|---|---|---|---|
| **Ring (no open)** | Opener (deviceType=2) | Unknown visitor rang the doorbell | Hue lights blink (warning pattern) |
| **Ring to open** | Opener (deviceType=2) | Authorized person arrived, door opened | Different blink + personalized announcement |
| **Door opened** | Smart Lock (deviceType=0) | Flat door was unlocked/opened | Chime or personalized announcement |

### Person Identification

For **ring to open** and **door opened** events, NukiBlinker queries the Nuki Bridge activity log (`GET /log`) to identify which user triggered the action. The user's registered name (as set in the Nuki app) is available as a `{name}` template variable in the TTS message.

Examples:
- Template: `"{name} llegó a casa"` → Announcement: "Nico llegó a casa"
- Template: `"{name} ha abierto la puerta"` → Announcement: "Ele ha abierto la puerta"
- If the name cannot be resolved (log unavailable, unknown trigger), falls back to a default: "Alguien llegó a casa".

Each event rule configures:
- Which **notification channels** to fire (checkboxes).
- Which **blink pattern** to use (alert, custom, or none).
- Which **audio** to play: chime (bundled sound), TTS (template message with `{name}`), or none.
- Whether to send a **HomeKit** notification.

Example configuration:

| | Ring (no open) | Ring to open | Door opened |
|---|---|---|---|
| Hue Lights | ✅ Red flash, 5x | ✅ Green flash, 2x | ❌ |
| Audio | ❌ | ✅ TTS "{name} llegó a casa" | ✅ Chime |
| HomeKit Notification | ✅ | ✅ | ❌ |

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
| **Audio** | Sound | Chime or TTS message on speakers | Google Nest (Chromecast) and/or HomePod (AirPlay) |
| **Apple HomeKit** | Push notification | Native doorbell alert on all Apple devices | iPhone/iPad/Watch/Mac |

### Audio (Chimes & Announcements)

Plays sounds on **Google Nest** and/or **Apple HomePod** speakers. Two audio modes:

- **Chime** (`mode: chime`): Plays a bundled chime sound (pleasant doorbell tone). No internet required.
- **TTS** (`mode: tts`): Plays a custom spoken message via `gTTS`. Requires internet. Message is configurable per event rule and supports `{name}` template variable for personalized announcements.

Speaker support:
- **Google Nest / Home**: Uses Chromecast protocol via `pychromecast`. Speakers auto-discovered on LAN.
- **Apple HomePod**: Uses AirPlay 2 via `pyatv`. Speakers auto-discovered on LAN.
- Volume can be set independently of the speaker's current volume.
- Both speaker types can be active simultaneously.

Bundled chime sounds are stored in `nukiblinker/sounds/`. Future: user-uploadable custom sounds.

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

**Access control**: The web UI is accessible from any private-network IP (localhost, Docker gateway, LAN). Requests from public IPs are rejected with `403 Forbidden`.

**Sections**:

1. **Nuki Bridge**
   - IP and port (auto-discovered if possible; manual fallback).
   - API token.
   - Device picker — select which Opener and/or Smart Lock to listen to.

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
   - One card per event type (Ring, Ring to open, Door opened).
   - Each card configures:
     - Hue: enable + blink pattern (alert/custom with color, flashes, interval).
     - Audio: mode (none / chime / TTS) + message text (for TTS mode).
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
- **Nuki Smart Lock**: optional Smart Lock ID filter.
- **Event rules**: per-event config (channels enabled, blink pattern, audio mode/message).
- **Server**: host and port for the callback listener.
- **Logging**: level, file path.

## Acceptance Criteria

1. **Event detection** — Events from the Nuki Opener and Smart Lock trigger the callback within 2 seconds.
2. **Event classification** — Ring, Ring to open, and Door opened are correctly distinguished and routed to the matching rule.
3. **Light blink** — Configured Hue lights blink with the per-event pattern within 1 second of receiving the callback.
4. **State restore** — After a custom blink sequence, lights return to their exact previous state (on/off, brightness, color).
5. **Audio** — Chime or TTS plays on selected Google Nest and/or HomePod speakers within 2 seconds.
6. **Person identification** — For ring-to-open and door-opened events, the user's name is resolved from the Nuki activity log and used in TTS templates.
7. **HomeKit** — Doorbell notification appears on all paired Apple devices within 2 seconds.
8. **Per-event rules** — Each event type has independently configurable channels, blink pattern, and audio mode/message.
9. **Resilience** — If a channel target is unreachable, NukiBlinker logs a warning but does not crash.
10. **Channel independence** — Each notification channel works independently; a failure in one does not block others.
11. **Idempotent startup** — Multiple restarts do not create duplicate callbacks on the Nuki Bridge.
12. **Config validation** — Invalid config is rejected at startup with a clear error message.
13. **Web UI** — Config page is accessible from private-network IPs (localhost, LAN). All settings are editable and persist to `config.yaml`.
14. **Auto-discovery** — Nuki Bridge, Hue Bridge, Chromecast speakers, and AirPlay speakers are auto-discovered when available.
15. **Test buttons** — Per-event "Test" button fires all enabled channels for that rule without a real doorbell event.
16. **Graceful shutdown** — `docker compose down` deregisters the Nuki callback before exiting.
17. **Pause/Resume** — Web UI pause button deregisters callback without stopping the service; resume re-registers it.
18. **Tests** — Unit tests cover event classification, person identification, all notification channels, event rules, config validation, web UI access control, and shutdown hook.
19. **Lint** — `make lint` passes with zero errors.

## Non-Goals (Current)

- No integration with Nuki Cloud API (local bridge only, except for bridge discovery).
- No Alexa support (no public local API for announcements).
- No multi-bridge support (single Nuki Bridge + single Hue Bridge).
- No door-opening automation — NukiBlinker is notification only, it never opens or locks doors.
- No remote access to the web UI from public IPs — private networks only (localhost, LAN).

## Future Considerations

- Support for multiple Hue Bridges or light groups with different patterns.
- Cooldown period to prevent rapid re-triggering.
- Additional Nuki event types (lock, unlock, battery low) as triggers.
- User-uploadable custom chime sounds via the web UI.
- Push notification fallback (e.g., Pushover, Telegram) when not home.
- Optional authentication for the web UI (to allow LAN-wide access).
- Per-person announcements if combined with a camera/face recognition system.
