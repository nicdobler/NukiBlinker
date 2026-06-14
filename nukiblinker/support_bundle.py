"""Build and deliver a diagnostic support bundle (#117).

A support bundle is a ZIP containing, for a chosen time window:
- ``app-log.txt``  — the slice of the rotating application log in the window,
- ``events.json``  — event-log entries in the window (full fidelity),
- ``events.csv``   — the same entries in a compact CSV,
- ``metadata.txt`` — window, app version and a **redacted** config summary.

GitHub's REST API cannot attach a binary directly to an issue, so the ZIP is
committed (base64) to ``support-bundles/<timestamp>.zip`` via the Contents API
and linked from a newly-created issue. Auth is a PAT with ``contents:write`` +
``issues:write`` (``github.token`` config or ``GITHUB_TOKEN`` env).

Timezone note: the application log uses **local** naive timestamps
(``logging`` default), while the event log stores **UTC**. The window is
resolved as timezone-aware datetimes and converted appropriately for each
source.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

from nukiblinker.config import MASK_SENTINEL, SECRET_FIELDS, summarize_config
from nukiblinker.logging_config import get_logger

logger = get_logger("support_bundle")

_GITHUB_API = "https://api.github.com"
_LOG_TS_LEN = len("YYYY-MM-DD HH:MM:SS")
_LOG_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


class SupportBundleError(Exception):
    """Raised for user-actionable support-bundle failures (bad input / GitHub)."""


def app_version() -> str:
    """Return the installed package version, falling back to a constant."""
    try:
        from importlib.metadata import version

        return version("nukiblinker")
    except Exception:
        return "0.1.0"


# ---------------------------------------------------------------------------
# Window resolution
# ---------------------------------------------------------------------------


def _parse_dt(value: str, default_tz: timezone) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_tz)
    return dt


def resolve_window(
    *,
    reference: str | None = None,
    window_minutes: int = 15,
    start: str | None = None,
    end: str | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Resolve the bundle's time window as timezone-aware datetimes.

    Either provide explicit ``start``/``end`` ISO strings, or a ``reference``
    point (defaults to *now*) with a ``window_minutes`` half-width applied
    before and after. Naive ISO inputs are interpreted in the local timezone.
    """
    local_tz = (now or datetime.now()).astimezone().tzinfo or timezone.utc

    if start and end:
        s = _parse_dt(start, local_tz)
        e = _parse_dt(end, local_tz)
    else:
        ref = _parse_dt(reference, local_tz) if reference else (now or datetime.now(local_tz))
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=local_tz)
        half = timedelta(minutes=max(1, int(window_minutes)))
        s, e = ref - half, ref + half

    if e < s:
        raise SupportBundleError("window end is before start")
    return s, e


# ---------------------------------------------------------------------------
# App-log slicing (local naive timestamps)
# ---------------------------------------------------------------------------


def _parse_log_timestamp(line: str) -> datetime | None:
    """Parse the leading ``YYYY-MM-DD HH:MM:SS`` of a log line, or None."""
    if len(line) < _LOG_TS_LEN:
        return None
    try:
        return datetime.strptime(line[:_LOG_TS_LEN], _LOG_TS_FORMAT)
    except ValueError:
        return None


def slice_app_log(text: str, start_naive: datetime, end_naive: datetime) -> str:
    """Return the lines of ``text`` whose timestamp is within the window.

    Continuation lines (no parseable timestamp, e.g. tracebacks) inherit the
    inclusion decision of the most recent timestamped line, so multi-line
    records stay intact. ``start``/``end`` are naive (local) datetimes.
    """
    out: list[str] = []
    include = False
    for line in text.splitlines():
        ts = _parse_log_timestamp(line)
        if ts is not None:
            include = start_naive <= ts <= end_naive
        if include:
            out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Event serialisation
# ---------------------------------------------------------------------------


def events_to_json(entries: list) -> str:
    return json.dumps([e.to_dict() for e in entries], indent=2, ensure_ascii=False)


def events_to_csv(entries: list) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["timestamp", "event_type", "nuki_id", "valid", "delay_seconds", "reason", "actions"]
    )
    for e in entries:
        payload = e.payload or {}
        vr = getattr(e, "validation_result", None)
        writer.writerow([
            e.timestamp.isoformat(),
            e.event_type or "",
            payload.get("nukiId", ""),
            getattr(vr, "valid", ""),
            getattr(vr, "delay_seconds", ""),
            getattr(vr, "reason", "") or "",
            " | ".join(e.actions or []),
        ])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Redaction + metadata
# ---------------------------------------------------------------------------


def redacted_config_yaml(config) -> str:
    """Return the config as YAML with every secret field masked (#117)."""
    data: dict[str, Any] = config.model_dump(mode="json")
    for section, key in SECRET_FIELDS:
        if data.get(section, {}).get(key):
            data[section][key] = MASK_SENTINEL
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _metadata_text(start: datetime, end: datetime, config) -> str:
    return (
        f"NukiBlinker support bundle\n"
        f"App version : {app_version()}\n"
        f"Window start: {start.isoformat()}\n"
        f"Window end  : {end.isoformat()}\n"
        f"Integrations: {summarize_config(config)}\n"
        f"\n"
        f"--- Redacted config ---\n"
        f"{redacted_config_yaml(config)}"
    )


def build_zip(*, app_log: str, events_json: str, events_csv: str, metadata: str) -> bytes:
    """Assemble the bundle ZIP in memory and return its bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.txt", metadata)
        zf.writestr("app-log.txt", app_log)
        zf.writestr("events.json", events_json)
        zf.writestr("events.csv", events_csv)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# GitHub client
# ---------------------------------------------------------------------------


class GitHubClient:
    """Minimal GitHub REST client for committing a file and opening an issue."""

    def __init__(self, token: str, repo: str) -> None:
        self._token = token
        self._repo = repo
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def commit_file(self, path: str, content: bytes, message: str) -> dict:
        """Create a file at ``path`` via the Contents API (base64)."""
        import base64

        url = f"{_GITHUB_API}/repos/{self._repo}/contents/{path}"
        body = {"message": message, "content": base64.b64encode(content).decode("ascii")}
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.put(url, headers=self._headers, json=body)
            r.raise_for_status()
            return r.json()

    async def create_issue(self, title: str, body: str) -> dict:
        url = f"{_GITHUB_API}/repos/{self._repo}/issues"
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(url, headers=self._headers, json={"title": title, "body": body})
            r.raise_for_status()
            return r.json()


def _issue_body(start: datetime, end: datetime, config, n_events: int, bundle_url: str | None) -> str:
    link = f"[`{bundle_url}`]({bundle_url})" if bundle_url else "(commit succeeded; URL unavailable)"
    return (
        f"Automated support bundle from NukiBlinker `{app_version()}`.\n\n"
        f"- **Window**: `{start.isoformat()}` → `{end.isoformat()}`\n"
        f"- **Event-log entries**: {n_events}\n"
        f"- **Integrations**: {summarize_config(config)}\n"
        f"- **Bundle (ZIP)**: {link}\n\n"
        f"<details><summary>Redacted config</summary>\n\n```yaml\n"
        f"{redacted_config_yaml(config)}```\n</details>\n"
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def build_and_send(
    config,
    clients,
    *,
    token: str,
    repo: str,
    reference: str | None = None,
    window_minutes: int | None = None,
    start: str | None = None,
    end: str | None = None,
    now: datetime | None = None,
    github_client: GitHubClient | None = None,
) -> dict:
    """Build the bundle for the window and deliver it as a GitHub issue.

    Returns a dict with ``status``, ``issue_url``, ``bundle_url``, ``events``
    and the resolved ``window``. Raises ``SupportBundleError`` on bad input or
    GitHub failures.
    """
    wm = window_minutes if window_minutes else config.github.default_window_minutes
    s_aware, e_aware = resolve_window(
        reference=reference, window_minutes=wm, start=start, end=end, now=now
    )

    # Event log (UTC-stored): query the range directly.
    event_log = getattr(clients, "event_log", None)
    entries = event_log.get_events_in_range(s_aware, e_aware) if event_log is not None else []
    events_json = events_to_json(entries)
    events_csv = events_to_csv(entries)

    # App log (local naive): slice the rotating file.
    s_local = s_aware.astimezone().replace(tzinfo=None)
    e_local = e_aware.astimezone().replace(tzinfo=None)
    app_log = ""
    file_path = config.logging.file_path
    if file_path:
        log_path = Path(file_path)
        if log_path.is_file():
            app_log = slice_app_log(
                log_path.read_text(encoding="utf-8", errors="replace"), s_local, e_local
            )
        else:
            app_log = f"(application log file not found: {file_path})"

    metadata = _metadata_text(s_aware, e_aware, config)
    zip_bytes = build_zip(
        app_log=app_log, events_json=events_json, events_csv=events_csv, metadata=metadata
    )

    client = github_client or GitHubClient(token, repo)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"support-bundles/{stamp}.zip"
    try:
        commit = await client.commit_file(path, zip_bytes, f"Add support bundle {stamp}")
        content = commit.get("content", {}) if isinstance(commit, dict) else {}
        bundle_url = content.get("html_url") or content.get("download_url")
        issue = await client.create_issue(
            f"Support bundle {stamp}",
            _issue_body(s_aware, e_aware, config, len(entries), bundle_url),
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            raise SupportBundleError(
                "GitHub rejected the token — check it has contents:write + issues:write scopes"
            ) from exc
        raise SupportBundleError(f"GitHub API error (HTTP {status})") from exc
    except httpx.HTTPError as exc:
        raise SupportBundleError("Could not reach GitHub — network error") from exc

    return {
        "status": "created",
        "issue_url": issue.get("html_url") if isinstance(issue, dict) else None,
        "bundle_url": bundle_url,
        "events": len(entries),
        "window": {"start": s_aware.isoformat(), "end": e_aware.isoformat()},
    }
