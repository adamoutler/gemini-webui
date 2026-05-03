import time
from src.services.process_engine import fetch_sessions_for_host, SSHConnectionManager
from src.shared_state import (
    session_listing_locks,
    session_listing_locks_lock,
    session_results_cache,
    session_results_cache_lock,
)


def test_fetch_sessions_latch(monkeypatch):
    host = {"target": "test-latch-host", "dir": "~"}
    cache_key = "ssh:test-latch-host:~"

    # 1. Populate cache
    with session_results_cache_lock:
        session_results_cache[cache_key] = {
            "output": "cached_sessions",
            "error": None,
            "timestamp": time.time(),
        }

    # 2. Simulate an active latch
    with session_listing_locks_lock:
        session_listing_locks[cache_key] = {"active": True, "timestamp": time.time()}

    # Track if Popen is called
    popen_called = False

    class DummyPopen:
        def __init__(self, *args, **kwargs):
            nonlocal popen_called
            popen_called = True
            self.pid = 1234
            self.returncode = 0
            self.stdout = None
            self.stderr = None

        def communicate(self, *args, **kwargs):
            return "output", "error"

    monkeypatch.setattr("src.services.process_engine.subprocess.Popen", DummyPopen)
    monkeypatch.setattr(
        SSHConnectionManager, "check_and_recover_connection", lambda *args: None
    )

    res = fetch_sessions_for_host(host, "/tmp")

    assert res == {
        "output": "cached_sessions",
        "error": None,
        "timestamp": session_results_cache[cache_key]["timestamp"],
    }
    assert not popen_called, "Popen should not be called when latch is active"


def test_fetch_sessions_timeout(monkeypatch):
    host = {"target": "test-timeout-host", "dir": "~"}
    cache_key = "ssh:test-timeout-host:~"

    # 1. Simulate an OLD active latch (older than 60s)
    with session_listing_locks_lock:
        session_listing_locks[cache_key] = {
            "active": True,
            "timestamp": time.time() - 65,
        }

    popen_called = False

    class DummyPopen:
        def __init__(self, *args, **kwargs):
            nonlocal popen_called
            popen_called = True
            self.pid = 99999
            self.returncode = 0
            self.stdout = None
            self.stderr = None

        def communicate(self, *args, **kwargs):
            return "new_output", ""

    monkeypatch.setattr("src.services.process_engine.subprocess.Popen", DummyPopen)
    monkeypatch.setattr(
        SSHConnectionManager, "check_and_recover_connection", lambda *args: None
    )

    res = fetch_sessions_for_host(host, "/tmp")

    assert popen_called, "Popen should be called because latch timed out"
    assert res["output"] == "new_output"

    # Verify latch is released after completion
    with session_listing_locks_lock:
        assert not session_listing_locks[cache_key]["active"]
