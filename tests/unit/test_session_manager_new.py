from unittest.mock import patch, MagicMock

# Import from current location for the pre-refactor test run
try:
    from src.services.session_store import SessionManager
    from src.models.session import Session
except ImportError:
    from src.app import Session, SessionManager


def test_add_and_get_session():
    manager = SessionManager()
    session = Session("tab-1", None, 1000, "user1", "Local")
    manager.add_session(session)

    # Should be retrievable
    retrieved = manager.get_session("tab-1", "user1")
    assert retrieved is not None
    assert retrieved.tab_id == "tab-1"

    # Should not be retrievable by wrong user
    assert manager.get_session("tab-1", "user2") is None

    # Should not retrieve non-existent
    assert manager.get_session("tab-2", "user1") is None


def test_remove_session():
    manager = SessionManager()
    session = Session("tab-1", None, 1000, "user1")
    manager.add_session(session)
    manager.sid_to_tabid["sid-1"] = "tab-1"
    manager.tabid_to_sids["tab-1"] = {"sid-1"}
    removed = manager.remove_session("tab-1", "user1")
    assert removed == session
    assert manager.get_session("tab-1", "user1") is None
    assert "sid-1" not in manager.sid_to_tabid
    assert "tab-1" not in manager.tabid_to_sids


def test_orphan_session():
    manager = SessionManager()
    session = Session("tab-1", None, 1000, "user1")
    manager.add_session(session)
    manager.orphan_session("tab-1")
    assert session.orphaned_at is not None
    # Note: sid_to_tabid is purposefully left alone or cleared externally in app.py


@patch("src.app.socketio.emit")
def test_reclaim_session(mock_emit):
    manager = SessionManager()

    # Before refactoring, it might use socketio.emit directly.
    # After refactoring, it should use an on_steal callback.
    # To support both, we can inject a mock on_steal if it accepts it.

    session = Session("tab-1", None, 1000, "user1")
    manager.add_session(session)

    # First claim
    if "on_steal" in SessionManager.reclaim_session.__code__.co_varnames:
        manager.reclaim_session("tab-1", "sid-1", "user1", on_steal=MagicMock())
    else:
        manager.reclaim_session("tab-1", "sid-1", "user1")

    assert manager.tabid_to_sids["tab-1"] == {"sid-1"}
    assert manager.sid_to_tabid["sid-1"] == "tab-1"

    # Second claim (steal)
    mock_on_steal = MagicMock()
    if "on_steal" in SessionManager.reclaim_session.__code__.co_varnames:
        manager.reclaim_session("tab-1", "sid-2", "user1", on_steal=mock_on_steal)
        mock_on_steal.assert_called_once_with("tab-1", "sid-1")
    else:
        manager.reclaim_session("tab-1", "sid-2", "user1")
        pass

    assert manager.tabid_to_sids["tab-1"] == {"sid-1", "sid-2"}
    assert manager.sid_to_tabid["sid-2"] == "tab-1"


def test_list_sessions():
    manager = SessionManager()
    s1 = Session("tab-1", None, 1000, "user1")
    s2 = Session("tab-2", None, 1001, "user1")
    s3 = Session("tab-3", None, 1002, "user2")
    manager.add_session(s1)
    manager.add_session(s2)
    manager.add_session(s3)

    user1_sessions = manager.list_sessions("user1")
    assert len(user1_sessions) == 2

    user2_sessions = manager.list_sessions("user2")
    assert len(user2_sessions) == 1
    assert user2_sessions[0]["tab_id"] == "tab-3"


def test_update_title():
    manager = SessionManager()
    session = Session("tab-1", None, 1000, "user1", "Local")
    manager.add_session(session)

    assert session.title == "Local"

    manager.update_title("tab-1", "Working...", "user1")
    assert session.title == "Working..."

    # Test invalid tab
    manager.update_title("invalid-tab", "Should Not Apply", "user1")
    assert session.title == "Working..."
