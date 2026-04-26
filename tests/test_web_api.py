"""End-to-end HTTP tests for the web UI API.

Spins the stdlib server up once per test session on a random port, then runs
each test against a freshly-truncated database. Uses httpx (already in deps)
for the client. No mocks — the server, DB, JWT, and bcrypt are all real.

Run with:  pytest tests/test_web_api.py -v
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import pytest
import platform

if platform.system() == "Windows":
    pytest.skip("Web API tests are not supported on Windows due to PTY requirements", allow_module_level=True)

# Make the project root importable so `from web import ...` works
_PKG = Path(__file__).resolve().parent.parent
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_ready(url: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code in (200, 503):
                return
        except httpx.HTTPError as exc:
            last_err = exc
        time.sleep(0.05)
    raise RuntimeError(f"server never became ready: {last_err}")


@pytest.fixture(scope="session")
def server_url() -> str:
    """Start the web server in a background thread for the test session."""
    tmpdir = tempfile.mkdtemp(prefix="cc_test_")
    db_path = os.path.join(tmpdir, "test.db")
    secret_path = os.path.join(tmpdir, "secret")
    # Set env BEFORE importing server so init reads the right paths
    os.environ["CHEETAHCLAWS_WEB_DB"] = db_path
    os.environ["CHEETAHCLAWS_WEB_SECRET"] = "test-secret-do-not-use-in-prod"
    os.environ["CHEETAHCLAWS_LOG_LEVEL"] = "WARNING"  # quiet during tests

    from web.server import start_web_server  # noqa: WPS433

    port = _free_port()
    threading.Thread(
        target=start_web_server,
        kwargs={"port": port, "host": "127.0.0.1", "no_auth": False},
        daemon=True,
    ).start()
    base = f"http://127.0.0.1:{port}"
    _wait_for_ready(f"{base}/health")
    return base


@pytest.fixture(autouse=True)
def fresh_db():
    """Truncate all tables between tests so each starts empty."""
    from web.db import init_db, _engine  # noqa: WPS433
    from web.models import Base
    init_db()
    # _engine is a module global set by init_db
    from web import db as _dbmod
    eng = _dbmod._engine
    assert eng is not None
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    # Also wipe the in-memory ChatSession cache so stale objects don't survive
    from web import api as _apimod
    _apimod._chat_sessions.clear()
    yield


def _client(base: str) -> httpx.Client:
    return httpx.Client(base_url=base, timeout=5.0, follow_redirects=False)


def _register(c: httpx.Client, username: str, password: str = "secret123"):
    return c.post("/api/auth/register",
                  json={"username": username, "password": password})


def _login(c: httpx.Client, username: str, password: str = "secret123"):
    return c.post("/api/auth/login",
                  json={"username": username, "password": password})


# ── Tests ────────────────────────────────────────────────────────────────


def test_health_returns_ok(server_url):
    with _client(server_url) as c:
        r = c.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["db"] == "ok"
        assert d["uptime_s"] >= 0


def test_metrics_prometheus_format(server_url):
    with _client(server_url) as c:
        r = c.get("/metrics")
        assert r.status_code == 200
        body = r.text
        assert "cheetahclaws_uptime_seconds " in body
        assert "cheetahclaws_requests_total " in body
        assert "# TYPE cheetahclaws_requests_total counter" in body


def test_bootstrap_empty_then_after_register(server_url):
    with _client(server_url) as c:
        assert c.get("/api/auth/bootstrap").json() == {
            "has_users": False, "no_auth": False,
        }
        r = _register(c, "alice")
        assert r.status_code == 200
        assert c.get("/api/auth/bootstrap").json()["has_users"] is True


def test_first_user_is_admin_second_is_not(server_url):
    with _client(server_url) as c:
        u1 = _register(c, "alice").json()["user"]
        # Different client so the cookie from register doesn't leak
        with _client(server_url) as c2:
            u2 = _register(c2, "bob").json()["user"]
        assert u1["is_admin"] is True
        assert u2["is_admin"] is False


def test_register_short_password_400(server_url):
    with _client(server_url) as c:
        r = c.post("/api/auth/register",
                   json={"username": "alice", "password": "12345"})
        assert r.status_code == 400


def test_register_duplicate_username_409(server_url):
    with _client(server_url) as c:
        _register(c, "alice")
        with _client(server_url) as c2:
            r = _register(c2, "alice")
            assert r.status_code == 409


def test_login_wrong_password_401(server_url):
    with _client(server_url) as c:
        _register(c, "alice")
        with _client(server_url) as c2:
            r = _login(c2, "alice", "WRONG")
            assert r.status_code == 401


def test_whoami_without_cookie_401(server_url):
    with _client(server_url) as c:
        assert c.get("/api/auth/whoami").status_code == 401


def test_register_then_whoami(server_url):
    with _client(server_url) as c:
        _register(c, "alice")  # cookie persists in this client
        r = c.get("/api/auth/whoami")
        assert r.status_code == 200
        assert r.json()["user"]["username"] == "alice"


def test_logout_clears_cookie(server_url):
    with _client(server_url) as c:
        _register(c, "alice")
        assert c.get("/api/auth/whoami").status_code == 200
        c.post("/api/auth/logout")
        # The Set-Cookie max-age=0 should clear the cookie in this client
        assert c.get("/api/auth/whoami").status_code == 401


def test_sessions_list_empty(server_url):
    with _client(server_url) as c:
        _register(c, "alice")
        r = c.get("/api/sessions")
        assert r.status_code == 200
        assert r.json() == {"sessions": []}


def test_create_session_via_prompt(server_url):
    with _client(server_url) as c:
        _register(c, "alice")
        r = c.post("/api/prompt",
                   json={"prompt": "", "session_id": ""})
        assert r.status_code == 200
        sid = r.json()["session_id"]
        assert len(sid) >= 8
        ls = c.get("/api/sessions").json()["sessions"]
        assert len(ls) == 1
        assert ls[0]["id"] == sid


def test_rename_session(server_url):
    with _client(server_url) as c:
        _register(c, "alice")
        sid = c.post("/api/prompt",
                     json={"prompt": "", "session_id": ""}).json()["session_id"]
        r = c.patch(f"/api/sessions/{sid}", json={"title": "My Project Notes"})
        assert r.status_code == 200
        assert r.json()["title"] == "My Project Notes"
        ls = c.get("/api/sessions").json()["sessions"]
        assert ls[0]["title"] == "My Project Notes"


def test_rename_requires_title(server_url):
    with _client(server_url) as c:
        _register(c, "alice")
        sid = c.post("/api/prompt",
                     json={"prompt": "", "session_id": ""}).json()["session_id"]
        r = c.patch(f"/api/sessions/{sid}", json={"title": "  "})
        assert r.status_code == 400


def test_delete_session(server_url):
    with _client(server_url) as c:
        _register(c, "alice")
        sid = c.post("/api/prompt",
                     json={"prompt": "", "session_id": ""}).json()["session_id"]
        r = c.request("DELETE", f"/api/sessions/{sid}")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert c.get("/api/sessions").json()["sessions"] == []


def test_export_session_markdown(server_url):
    with _client(server_url) as c:
        _register(c, "alice")
        sid = c.post("/api/prompt",
                     json={"prompt": "", "session_id": ""}).json()["session_id"]
        r = c.get(f"/api/sessions/{sid}/export")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        assert sid in r.text
        assert "# " in r.text  # has a heading


def test_cross_user_isolation(server_url):
    with _client(server_url) as ca:
        _register(ca, "alice")
        sid = ca.post("/api/prompt",
                      json={"prompt": "", "session_id": ""}).json()["session_id"]
    with _client(server_url) as cb:
        _register(cb, "bob")
        # Bob can't see Alice's session in the list
        assert cb.get("/api/sessions").json() == {"sessions": []}
        # Bob can't fetch it directly
        assert cb.get(f"/api/sessions/{sid}").status_code == 404
        # Bob can't delete it (returns ok:false)
        assert cb.request("DELETE",
                          f"/api/sessions/{sid}").json() == {"ok": False}


def test_session_persists_in_db_after_cache_clear(server_url):
    """Session metadata survives even when in-memory cache is cleared
    (simulates a server restart while user is still logged in)."""
    with _client(server_url) as c:
        _register(c, "alice")
        sid = c.post("/api/prompt",
                     json={"prompt": "", "session_id": ""}).json()["session_id"]
        c.patch(f"/api/sessions/{sid}", json={"title": "Persistent Title"})
        # Clear in-memory cache (simulates restart)
        from web import api as _apimod
        _apimod._chat_sessions.clear()
        # Listing still works (DB-backed)
        ls = c.get("/api/sessions").json()["sessions"]
        assert len(ls) == 1
        assert ls[0]["title"] == "Persistent Title"
        # Detail fetch hydrates from DB
        d = c.get(f"/api/sessions/{sid}").json()
        assert d["title"] == "Persistent Title"


def test_auth_required_for_chat_endpoints(server_url):
    with _client(server_url) as c:
        # No cookie → all chat endpoints return 401
        assert c.get("/api/sessions").status_code == 401
        assert c.post("/api/prompt", json={}).status_code == 401
        assert c.get("/api/sessions/abc").status_code == 401
        assert c.get("/api/models").status_code == 401


def test_metrics_counters_increment(server_url):
    with _client(server_url) as c:
        before = c.get("/metrics").text
        # Trigger a 401 and a successful registration
        c.get("/api/auth/whoami")  # 401
        _register(c, "alice")
        after = c.get("/metrics").text

        def _counter(text: str, name: str) -> int:
            for line in text.splitlines():
                if line.startswith(name + " "):
                    return int(line.split()[1])
            return -1

        assert _counter(after, "cheetahclaws_requests_total") > _counter(
            before, "cheetahclaws_requests_total")
        assert _counter(after, "cheetahclaws_requests_4xx") >= _counter(
            before, "cheetahclaws_requests_4xx") + 1
        assert _counter(after, "cheetahclaws_auth_registrations_total") >= 1


def test_cors_preflight_for_unknown_origin(server_url):
    """Preflight OPTIONS should respond 204 (server replies even without CORS)."""
    with _client(server_url) as c:
        r = c.request("OPTIONS", "/api/sessions",
                      headers={"Origin": "http://example.com",
                               "Access-Control-Request-Method": "GET"})
        assert r.status_code == 204
