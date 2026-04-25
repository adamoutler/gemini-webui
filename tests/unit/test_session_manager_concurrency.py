import pytest
import threading
from unittest.mock import patch
from src.services.session_store import SessionManager
from src.models.session import Session


@pytest.mark.timeout(60)
def test_session_manager_concurrency():
    """
    Test adding, retrieving, and deleting sessions concurrently
    to ensure there are no dictionary size change exceptions during iteration.
    """
    manager = SessionManager()

    def worker(i):
        tab_id = f"tab_{i}"
        sid = f"sid_{i}"
        user_id = "user1"
        session = Session(tab_id, None, 1000 + i, user_id)

        # Add session
        manager.add_session(session)

        # Reclaim (updates mapping)
        manager.reclaim_session(tab_id, sid, user_id)

        # Iterate over sessions (this is what typically throws RuntimeError without locks)
        manager.list_sessions(user_id)

        # Remove session
        manager.remove_session(tab_id, user_id)

    threads = []
    for i in range(100):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # All sessions should be removed
    assert len(manager.sessions) == 0
    assert len(manager.sid_to_tabid) == 0
    assert len(manager.tabid_to_sids) == 0


@pytest.mark.timeout(60)
def test_session_manager_mapping_integrity():
    manager = SessionManager()
    s1 = Session("tab1", None, 1000, "user1")
    manager.add_session(s1)

    # 1. Normal claim
    manager.reclaim_session("tab1", "sid1", "user1")
    assert manager.sid_to_tabid.get("sid1") == "tab1"
    assert "sid1" in manager.tabid_to_sids.get("tab1", set())

    # 2. Steal by another SID
    manager.reclaim_session("tab1", "sid2", "user1")
    # Old sid should be gone
    assert "sid1" in manager.sid_to_tabid
    # New sid should be mapped
    assert manager.sid_to_tabid.get("sid2") == "tab1"
    assert "sid2" in manager.tabid_to_sids.get("tab1", set())

    # 3. Orphan
    manager.remove_session("tab1", "user1")
    assert not manager.tabid_to_sids.get("tab1", set())
