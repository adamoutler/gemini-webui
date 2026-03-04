import pytest
import json
import os
import signal
from unittest.mock import patch
from src.app import app, init_app, session_manager, Session

@pytest.fixture(autouse=True)
def setup_teardown():
    session_manager.sessions.clear()
    session_manager.sid_to_tabid.clear()
    session_manager.tabid_to_sid.clear()
    yield
    session_manager.sessions.clear()
    session_manager.sid_to_tabid.clear()
    session_manager.tabid_to_sid.clear()

@pytest.fixture
def client(test_data_dir, monkeypatch):
    app.config['TESTING'] = True
    app.config['DATA_DIR'] = str(test_data_dir)
    app.config['BYPASS_AUTH_FOR_TESTING'] = 'true'
    monkeypatch.setenv('BYPASS_AUTH_FOR_TESTING', 'true')
    app.config['WTF_CSRF_ENABLED'] = False
    
    # Force initialization to set up globals and paths
    with app.app_context():
        init_app()
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['user_id'] = 'admin'
        yield client

def test_list_management_sessions(client):
    # Add a mock session
    tab_id = "test-tab-id"
    user_id = "admin"
    mock_session = Session(tab_id, 999, 12345, user_id)
    session_manager.add_session(mock_session)
    
    response = client.get('/api/management/sessions')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data) >= 1
    assert any(s['tab_id'] == tab_id for s in data)
    
    # Cleanup
    session_manager.remove_session(tab_id)

def test_terminate_managed_session(client):
    # Add a mock session
    tab_id = "terminate-tab-id"
    pid = 99999
    user_id = "admin"
    mock_session = Session(tab_id, 888, pid, user_id)
    session_manager.add_session(mock_session)

    with patch('os.kill') as mock_kill, patch('os.waitpid') as mock_waitpid:
        response = client.delete(f'/api/management/sessions/{tab_id}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'success'

        mock_kill.assert_called_once_with(pid, signal.SIGKILL)
        mock_waitpid.assert_called_once_with(pid, 0)

        # Verify session is removed
        assert session_manager.get_session(tab_id) is None

def test_terminate_managed_session_not_found(client):
    response = client.delete('/api/management/sessions/non-existent')
    assert response.status_code == 404
    data = json.loads(response.data)
    assert "error" in data
