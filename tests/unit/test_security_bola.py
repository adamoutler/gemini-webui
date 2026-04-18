from src.session_manager import Session


def test_bola_get_sessions(client):
    # Important: import session_manager here because conftest reloads src.app
    from src.app import session_manager

    # Setup two different users
    user_a = "user_A"
    user_b = "user_B"

    # Add dummy sessions directly to the session manager
    session_manager.sessions.clear()
    session_manager.sid_to_tabid.clear()
    session_manager.tabid_to_sids.clear()

    mock_session_a = Session("tab_A1", None, 1001, user_a)
    session_manager.add_session(mock_session_a)

    mock_session_b = Session("tab_B1", None, 1002, user_b)
    session_manager.add_session(mock_session_b)

    # User B tries to fetch sessions, should only see tab_B1
    with client.session_transaction() as sess:
        sess["user_id"] = user_b
        sess["authenticated"] = True

    response = client.get("/api/management/sessions")
    assert response.status_code == 200
    data = response.json

    # Assert User A's session is not present
    tab_ids = [s["tab_id"] for s in data]
    assert "tab_B1" in tab_ids
    assert "tab_A1" not in tab_ids

    # Ensure the session still exists in the manager
    assert "tab_A1" in session_manager.sessions


def test_bola_websocket_events(client):
    from src.app import session_manager

    # Testing the session manager directly shows the protection
    user_a = "user_A"
    user_b = "user_B"

    session_manager.sessions.clear()
    session_manager.sid_to_tabid.clear()
    session_manager.tabid_to_sids.clear()

    mock_session_a = Session("tab_A1", None, 1001, user_a)
    session_manager.add_session(mock_session_a)

    # Ensure get_session fails if user_id does not match
    assert session_manager.get_session("tab_A1", user_b) is None
    assert session_manager.get_session("tab_A1", user_a) is not None
