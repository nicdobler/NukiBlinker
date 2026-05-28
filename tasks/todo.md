# Tasks

---

## Project Setup

**Branch**: `chore/project-setup`

- [x] Create project scaffolding (Agents.md, pyproject.toml, Makefile, .gitignore, Dockerfile)
- [x] Write product spec (specs/product-spec.md)
- [x] Write tech spec (specs/tech-spec.md)
- [x] Create workflows (.windsurf/workflows/*.md)
- [x] Create README.md and CHANGELOG.md
- [x] Create example config (config.example.yaml)
- [x] User approval of specs
- [ ] `poetry install` + verify tooling works (Mac)

---

## Core Implementation

**Branch**: `feat/core-implementation` | **PR**: TBD

### Phase 1 — Foundation (no external deps beyond FastAPI/httpx)
- [x] 1. `logging_config.py` — structured logging setup
- [x] 2. `config.py` — Pydantic models + load/save YAML
- [x] 3. `tests/test_config.py` — validation, defaults, load, save
- [x] 4. `event_router.py` — classify() + resolve_person() + dispatch()
- [x] 5. `tests/test_event_router.py` — all 3 event types + person resolution
- [x] 6. `nuki_client.py` — Nuki Bridge HTTP API (callbacks, devices, log)
- [x] 7. `tests/test_nuki_client.py` — mock httpx
- [x] 8. `hue_client.py` — Hue Bridge v1 REST (alert, custom blink, list)
- [x] 9. `tests/test_hue_client.py` — mock httpx

### Phase 2 — Audio & Speakers
- [x] 10. `audio.py` — TTS generation + chime + {name} template
- [x] 11. `tests/test_audio.py` — template, TTS mock, chime resolution
- [x] 12. `chromecast_client.py` — play audio on Chromecast speakers
- [x] 13. `tests/test_chromecast.py` — mock pychromecast
- [x] 14. `airplay_client.py` — play audio on AirPlay/HomePod speakers
- [x] 15. `tests/test_airplay.py` — mock pyatv

### Phase 3 — HomeKit & Notifier
- [x] 16. `homekit_service.py` — HAP-python doorbell accessory
- [x] 17. `tests/test_homekit.py` — mock HAP-python
- [x] 18. `notifier.py` — orchestrate channels per event rule
- [x] 19. `tests/test_notifier.py` — dispatch + failure isolation

### Phase 4 — Server & Web UI
- [x] 20. `server.py` — FastAPI callback endpoint + health
- [x] 21. `tests/test_server.py` — callback routing
- [x] 22. `discovery.py` — auto-discovery for all devices
- [x] 23. `tests/test_discovery.py` — mock zeroconf
- [x] 24. `web_ui.py` — API routes + localhost guard
- [x] 25. `tests/test_web_ui.py` — routes + 403 access control

### Phase 5 — Entry Point & Lifecycle
- [x] 26. `__main__.py` — startup, shutdown hook, pause/resume
- [x] 27. `tests/test_lifecycle.py` — startup, shutdown, pause/resume
- [x] 28. `static/index.html` — web UI SPA
- [x] 29. Update `config.example.yaml`, `pyproject.toml` deps, `Dockerfile`
- [x] 30. Update `README.md`, `CHANGELOG.md`

### Next
- [ ] `poetry install` + `make test` + `make lint` on Mac
- [ ] Fix any test/lint issues
- [ ] Open PR to main
