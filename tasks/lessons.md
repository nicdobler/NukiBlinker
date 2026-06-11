# Lessons

## 2026-06-11 — Lint break pushed from work laptop
- **Mistake**: Pushed a log line >120 chars; CI lint (flake8 E501) failed on PR #75 (issues #76, #78).
- **Rule**: On the work laptop (no `make lint` allowed), manually check that new/edited lines stay ≤120 chars before committing — especially long log/f-string lines.

## 2026-06-11 — Mocked Clients hid missing attributes
- **Mistake**: Features merged with `event_log`/`event_validator`/`night_mode` used in `server.py`/`web_ui.py` but never built in `Clients` (#73). Tests passed because they used `MagicMock()` for clients.
- **Rule**: When adding services consumed via the `Clients` container, add a non-mocked `_build_clients` test asserting the attribute exists (see `test_event_pipeline_services_always_created`).

## 2026-06-11 — pytest -rP output misread as failures
- **Note**: `pytest -rP` prints captured logs of *passing* tests; ERROR/WARNING lines from negative-path tests are expected. Check the final summary line (`N passed`) before assuming failures.

## 2026-06-12 — Added redundant config option (homekit.address)
- **Mistake**: Added a new `homekit.address` config field when `server.public_host` + `get_public_host()` already expressed the same intent (LAN IP for externally-reachable endpoints).
- **Rule**: Before adding a config field, scan `config.py` for an existing option covering the same concept and reuse it. One concept = one config knob.
