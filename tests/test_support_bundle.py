"""Tests for nukiblinker.support_bundle and the /api/support/github-issue endpoint (#117)."""

import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from nukiblinker import support_bundle as sb
from nukiblinker.config import AppConfig
from nukiblinker.event_log import EventLog, EventLogEntry
from nukiblinker.event_validator import ValidationResult
from nukiblinker.server import create_app
from nukiblinker.web_ui import mount_web_ui


def _entry(ts, nuki=1, event_type="ring"):
    return EventLogEntry(
        timestamp=ts,
        event_type=event_type,
        payload={"nukiId": nuki},
        actions=["Hue lights blinked"],
        validation_result=ValidationResult(valid=True, delay_seconds=1.0, reason="ok"),
    )


class TestResolveWindow:
    def test_reference_plus_window(self):
        s, e = sb.resolve_window(reference="2026-06-14T12:00:00+00:00", window_minutes=15)
        assert (e - s) == timedelta(minutes=30)

    def test_explicit_start_end(self):
        s, e = sb.resolve_window(
            start="2026-06-14T12:00:00+00:00", end="2026-06-14T12:30:00+00:00"
        )
        assert (e - s) == timedelta(minutes=30)

    def test_end_before_start_raises(self):
        with pytest.raises(sb.SupportBundleError):
            sb.resolve_window(
                start="2026-06-14T12:30:00+00:00", end="2026-06-14T12:00:00+00:00"
            )

    def test_default_now_window(self):
        s, e = sb.resolve_window(window_minutes=10)
        assert (e - s) == timedelta(minutes=20)


class TestSliceAppLog:
    def test_filters_by_window_and_keeps_continuations(self):
        text = "\n".join([
            "2026-06-14 11:50:00 [INFO] x: before",
            "2026-06-14 12:00:00 [INFO] x: inside",
            "    Traceback continuation of inside",
            "2026-06-14 12:40:00 [INFO] x: after",
        ])
        start = datetime(2026, 6, 14, 11, 55, 0)
        end = datetime(2026, 6, 14, 12, 5, 0)
        out = sb.slice_app_log(text, start, end)
        assert "inside" in out
        assert "Traceback continuation" in out  # continuation inherits inclusion
        assert "before" not in out
        assert "after" not in out


class TestRedaction:
    def test_secrets_masked(self):
        cfg = AppConfig()
        cfg.nuki.api_token = "NUKI_SECRET_TOKEN"
        cfg.hue.api_key = "HUE_SECRET_KEY"
        cfg.github.token = "GH_SECRET_TOKEN"
        out = sb.redacted_config_yaml(cfg)
        assert "NUKI_SECRET_TOKEN" not in out
        assert "HUE_SECRET_KEY" not in out
        assert "GH_SECRET_TOKEN" not in out
        assert "***" in out


class TestBuildZip:
    def test_contains_expected_files(self):
        data = sb.build_zip(
            app_log="logline", events_json="[]", events_csv="h\n", metadata="meta"
        )
        zf = zipfile.ZipFile(io.BytesIO(data))
        assert set(zf.namelist()) == {"metadata.txt", "app-log.txt", "events.json", "events.csv"}
        assert zf.read("app-log.txt").decode() == "logline"


class TestEventsSerialisation:
    def test_csv_and_json(self):
        ts = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)
        entries = [_entry(ts, nuki=42)]
        csv_out = sb.events_to_csv(entries)
        assert "nuki_id" in csv_out and "42" in csv_out
        json_out = sb.events_to_json(entries)
        assert '"nukiId": 42' in json_out


class _FakeGitHub:
    """Captures the commit + issue calls without touching the network."""

    def __init__(self, *args, **kwargs):
        self.committed = None
        self.issue = None
        self.ensured_branch = None
        self.commit_branch = None

    async def ensure_branch(self, branch):
        self.ensured_branch = branch

    async def commit_file(self, path, content, message, branch=None):
        self.committed = (path, content, message)
        self.commit_branch = branch
        return {"content": {"html_url": f"https://github.com/x/y/blob/{branch or 'main'}/{path}"}}

    async def create_issue(self, title, body):
        self.issue = (title, body)
        return {"html_url": "https://github.com/x/y/issues/1"}


@pytest.mark.asyncio
async def test_build_and_send(tmp_path):
    log = EventLog(persist_to_file=False)
    in_window = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)
    out_window = datetime(2026, 6, 14, 9, 0, 0, tzinfo=timezone.utc)
    log.store_entry(_entry(in_window))
    log.store_entry(_entry(out_window))

    clients = MagicMock()
    clients.event_log = log

    log_file = tmp_path / "nukiblinker.log"
    log_file.write_text(
        "2026-06-14 12:00:00 [INFO] x: hello\n2026-06-14 09:00:00 [INFO] x: old\n",
        encoding="utf-8",
    )
    cfg = AppConfig()
    cfg.logging.file_path = str(log_file)
    cfg.github.token = "tok"
    cfg.nuki.api_token = "SUPER_SECRET_TOKEN"

    fake = _FakeGitHub()
    result = await sb.build_and_send(
        cfg, clients, token="tok", repo="x/y",
        reference="2026-06-14T12:00:00+00:00", window_minutes=15,
        github_client=fake,
    )

    assert result["status"] == "created"
    assert result["events"] == 1  # only the in-window event
    assert result["issue_url"].endswith("/issues/1")

    # A ZIP was committed under support-bundles/ on the dedicated branch (#149).
    assert fake.ensured_branch == "support-bundles"
    assert fake.commit_branch == "support-bundles"
    path, content, _ = fake.committed
    assert path.startswith("support-bundles/") and path.endswith(".zip")
    zf = zipfile.ZipFile(io.BytesIO(content))
    assert set(zf.namelist()) == {"metadata.txt", "app-log.txt", "events.json", "events.csv"}

    # The issue body redacts secrets.
    _, body = fake.issue
    assert "SUPER_SECRET_TOKEN" not in body


@pytest.mark.asyncio
async def test_build_and_send_github_auth_error(tmp_path):
    import httpx

    class _AuthFail:
        def __init__(self, *a, **k):
            pass

        async def ensure_branch(self, *a, **k):
            pass

        async def commit_file(self, *a, **k):
            req = httpx.Request("PUT", "https://api.github.com/x")
            resp = httpx.Response(401, request=req)
            raise httpx.HTTPStatusError("unauthorized", request=req, response=resp)

        async def create_issue(self, *a, **k):  # pragma: no cover - not reached
            return {}

    cfg = AppConfig()
    clients = MagicMock()
    clients.event_log = EventLog(persist_to_file=False)
    with pytest.raises(sb.SupportBundleError, match="scopes"):
        await sb.build_and_send(
            cfg, clients, token="bad", repo="x/y",
            reference="2026-06-14T12:00:00+00:00", window_minutes=5,
            github_client=_AuthFail(),
        )


class TestGithubErrorDetail:
    def test_json_message(self):
        import httpx

        resp = httpx.Response(404, json={"message": "Not Found"},
                              request=httpx.Request("PUT", "https://api.github.com/x"))
        assert sb._github_error_detail(resp) == "Not Found"

    def test_json_message_with_errors(self):
        import httpx

        resp = httpx.Response(
            422,
            json={"message": "Validation Failed", "errors": [{"field": "sha"}]},
            request=httpx.Request("PUT", "https://api.github.com/x"),
        )
        detail = sb._github_error_detail(resp)
        assert "Validation Failed" in detail and "sha" in detail

    def test_non_json_body(self):
        import httpx

        resp = httpx.Response(500, text="upstream boom",
                              request=httpx.Request("PUT", "https://api.github.com/x"))
        assert sb._github_error_detail(resp) == "upstream boom"

    def test_empty_body(self):
        import httpx

        resp = httpx.Response(503, request=httpx.Request("PUT", "https://api.github.com/x"))
        assert sb._github_error_detail(resp) == "no response body"


@pytest.mark.asyncio
async def test_build_and_send_github_404_includes_detail(tmp_path):
    """A 404 (bad repo / no access) surfaces the repo, status and GitHub message (#149)."""
    import httpx

    class _NotFound:
        def __init__(self, *a, **k):
            pass

        async def ensure_branch(self, *a, **k):
            pass

        async def commit_file(self, *a, **k):
            req = httpx.Request("PUT", "https://api.github.com/repos/x/y/contents/z")
            resp = httpx.Response(404, json={"message": "Not Found"}, request=req)
            raise httpx.HTTPStatusError("not found", request=req, response=resp)

        async def create_issue(self, *a, **k):  # pragma: no cover - not reached
            return {}

    cfg = AppConfig()
    clients = MagicMock()
    clients.event_log = EventLog(persist_to_file=False)
    with pytest.raises(sb.SupportBundleError) as exc:
        await sb.build_and_send(
            cfg, clients, token="tok", repo="x/y",
            reference="2026-06-14T12:00:00+00:00", window_minutes=5,
            github_client=_NotFound(),
        )
    msg = str(exc.value)
    assert "x/y" in msg and "404" in msg and "Not Found" in msg


@pytest.mark.asyncio
async def test_build_and_send_github_generic_error_includes_detail(tmp_path):
    """A non-auth/non-404 error includes the HTTP status and GitHub message (#149)."""
    import httpx

    class _ServerError:
        def __init__(self, *a, **k):
            pass

        async def ensure_branch(self, *a, **k):
            pass

        async def commit_file(self, *a, **k):
            req = httpx.Request("PUT", "https://api.github.com/repos/x/y/contents/z")
            resp = httpx.Response(422, json={"message": "Validation Failed"}, request=req)
            raise httpx.HTTPStatusError("unprocessable", request=req, response=resp)

        async def create_issue(self, *a, **k):  # pragma: no cover - not reached
            return {}

    cfg = AppConfig()
    clients = MagicMock()
    clients.event_log = EventLog(persist_to_file=False)
    with pytest.raises(sb.SupportBundleError, match="422") as exc:
        await sb.build_and_send(
            cfg, clients, token="tok", repo="x/y",
            reference="2026-06-14T12:00:00+00:00", window_minutes=5,
            github_client=_ServerError(),
        )
    assert "Validation Failed" in str(exc.value)


class TestGitHubClientBranch:
    """The bundle is committed to a dedicated branch to dodge default-branch rulesets (#149)."""

    @pytest.mark.asyncio
    async def test_ensure_branch_creates_when_missing(self):
        calls = []
        created_body = {}

        def handler(request):
            calls.append((request.method, request.url.path))
            p = request.url.path
            if request.method == "GET" and p == "/repos/x/y/branches/support-bundles":
                return httpx.Response(404, json={"message": "Branch not found"})
            if request.method == "GET" and p == "/repos/x/y":
                return httpx.Response(200, json={"default_branch": "main"})
            if request.method == "GET" and p == "/repos/x/y/git/ref/heads/main":
                return httpx.Response(200, json={"object": {"sha": "abc123"}})
            if request.method == "POST" and p == "/repos/x/y/git/refs":
                created_body.update(json.loads(request.content))
                return httpx.Response(201, json={"ref": "refs/heads/support-bundles"})
            return httpx.Response(500)  # pragma: no cover

        client = sb.GitHubClient("tok", "x/y", transport=httpx.MockTransport(handler))
        await client.ensure_branch("support-bundles")

        assert ("POST", "/repos/x/y/git/refs") in calls
        assert created_body == {"ref": "refs/heads/support-bundles", "sha": "abc123"}

    @pytest.mark.asyncio
    async def test_ensure_branch_noop_when_exists(self):
        calls = []

        def handler(request):
            calls.append((request.method, request.url.path))
            if request.url.path == "/repos/x/y/branches/support-bundles":
                return httpx.Response(200, json={"name": "support-bundles"})
            return httpx.Response(500)  # pragma: no cover — must not be reached

        client = sb.GitHubClient("tok", "x/y", transport=httpx.MockTransport(handler))
        await client.ensure_branch("support-bundles")

        assert calls == [("GET", "/repos/x/y/branches/support-bundles")]

    @pytest.mark.asyncio
    async def test_commit_file_targets_branch(self):
        captured = {}

        def handler(request):
            captured["path"] = request.url.path
            captured["body"] = json.loads(request.content)
            return httpx.Response(201, json={"content": {"html_url": "u"}})

        client = sb.GitHubClient("tok", "x/y", transport=httpx.MockTransport(handler))
        await client.commit_file("support-bundles/z.zip", b"data", "msg", branch="support-bundles")

        assert captured["body"]["branch"] == "support-bundles"
        assert "content" in captured["body"]


@pytest.mark.asyncio
async def test_build_and_send_ruleset_409(tmp_path):
    """A 409 from a branch ruleset yields an actionable error mentioning the ruleset (#149)."""
    class _Conflict:
        def __init__(self, *a, **k):
            pass

        async def ensure_branch(self, *a, **k):
            pass

        async def commit_file(self, *a, **k):
            req = httpx.Request("PUT", "https://api.github.com/repos/x/y/contents/z")
            resp = httpx.Response(
                409, json={"message": "Repository rule violations found"}, request=req
            )
            raise httpx.HTTPStatusError("conflict", request=req, response=resp)

        async def create_issue(self, *a, **k):  # pragma: no cover - not reached
            return {}

    cfg = AppConfig()
    clients = MagicMock()
    clients.event_log = EventLog(persist_to_file=False)
    with pytest.raises(sb.SupportBundleError, match="ruleset") as exc:
        await sb.build_and_send(
            cfg, clients, token="tok", repo="x/y",
            reference="2026-06-14T12:00:00+00:00", window_minutes=5,
            github_client=_Conflict(),
        )
    assert "support-bundles" in str(exc.value)


class TestSupportEndpoint:
    @pytest.fixture
    def client(self, tmp_path):
        cfg = AppConfig()
        clients = MagicMock()
        clients.event_log = EventLog(persist_to_file=False)
        app = create_app(cfg, clients)
        mount_web_ui(app, str(tmp_path / "config.yaml"))
        app.state.allowed_hosts = {"127.0.0.1", "::1", "localhost", "testclient"}
        return TestClient(app)

    def test_no_token_returns_400(self, client):
        r = client.post("/api/support/github-issue", json={})
        assert r.status_code == 400
        assert "token" in r.json()["error"].lower()

    def test_success(self, client, monkeypatch):
        client.app.state.config.github.token = "tok"

        async def fake_send(*args, **kwargs):
            return {
                "status": "created",
                "issue_url": "https://github.com/x/y/issues/2",
                "bundle_url": "https://github.com/x/y/blob/main/support-bundles/z.zip",
                "events": 3,
                "window": {},
            }

        monkeypatch.setattr("nukiblinker.support_bundle.build_and_send", fake_send)
        r = client.post("/api/support/github-issue", json={"window_minutes": 10})
        assert r.status_code == 200
        assert r.json()["issue_url"].endswith("/issues/2")
        assert r.json()["events"] == 3

    def test_bundle_error_returns_400(self, client, monkeypatch):
        client.app.state.config.github.token = "tok"

        async def fake_send(*args, **kwargs):
            raise sb.SupportBundleError("window end is before start")

        monkeypatch.setattr("nukiblinker.support_bundle.build_and_send", fake_send)
        r = client.post("/api/support/github-issue", json={"start": "b", "end": "a"})
        assert r.status_code == 400
        assert "window" in r.json()["error"].lower()
