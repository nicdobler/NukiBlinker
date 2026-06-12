# Lessons

## 2026-06-12 — base36.dumps() returns bytes in CI environment
- **Mistake**: Assumed `base36.dumps()` returns a string, but in the CI environment it returns bytes. Using it directly in an f-string caused `string argument expected, got 'bytes'`.
- **Rule**: Always handle library return types defensively. Use `isinstance(x, bytes)` and `.decode()` when a library might return bytes or str depending on version/environment.

## 2026-06-12 — pyqrcode writes bytes, not strings
- **Mistake**: Used `io.StringIO()` for pyqrcode output, but pyqrcode internally uses `write_bytes()` to write bytes to the file object. `StringIO` expects strings, causing `TypeError: string argument expected, got 'bytes'`.
- **Rule**: Check whether a library writes bytes or strings before choosing between `BytesIO` and `StringIO`. When in doubt, check the library source or use `BytesIO` and decode.

## 2026-06-12 — pyqrcode API mismatch
- **Mistake**: Called `qr.svg(scale=4, xmldecl=False, omithw=True)` without the required `file` parameter. The pyqrcode library's `svg()` method requires a file-like object to write to, not returning a string directly.
- **Rule**: When using library methods that write to files, check the signature carefully. Use `io.StringIO()` / `io.BytesIO()` to capture output as a string when needed.

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

## 2026-06-12 - HomeKit service changes on a paired standalone accessory
- **Mistake**: Added a second ProgrammableSwitchEvent service (StatelessProgrammableSwitch) without ServiceLabelIndex; iOS paired OK, then rejected the attribute DB and silently dropped the accessory. Also assumed iOS would treat a service-list change as an in-place update; it dropped the accessory instead, leaving an orphaned pairing (paired_clients set, no QR shown).
- **Rule**: When an accessory has 2+ services with ProgrammableSwitchEvent, set ServiceLabelIndex on the switch and mark the main service primary. Before deploying service-list changes to a paired accessory, remove it from the Home app first (protocol unpair), then deploy and re-pair.
