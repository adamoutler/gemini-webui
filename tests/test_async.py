import pytest
from unittest.mock import MagicMock, patch
import os
import signal
from src.app import pty_restart, cleanup_orphaned_ptys, background_session_preloader, session_results_cache

@pytest.fixture
def mock_socketio():
    with patch('src.app.socketio') as mock:
        yield mock

@pytest.fixture
def mock_pty():
    with patch('src.app.pty.fork') as mock_fork:
        yield mock_fork

def test_cleanup_orphaned_ptys(mock_socketio):
    # Ensure it breaks loop
    os.environ['BYPASS_AUTH_FOR_TESTING'] = 'true'
    
    # Mock some ptys
    from src.app import session_manager, Session
    import time
    
    # 1. Active PTY
    active_session = Session('active', 4, 123, 'admin')
    session_manager.add_session(active_session)
    
    # 2. Orphaned PTY (old)
    old_orphan = Session('old_orphan', 5, 124, 'admin')
    old_orphan.orphaned_at = time.time() - 100 # 100s ago
    session_manager.add_session(old_orphan)
    
    # 3. Orphaned PTY (new)
    new_orphan = Session('new_orphan', 6, 125, 'admin')
    new_orphan.orphaned_at = time.time() - 10 # 10s ago
    session_manager.add_session(new_orphan)

    with patch('os.kill') as mock_kill, patch('os.waitpid') as mock_wait:
        cleanup_orphaned_ptys()
        
        # Should have killed 124
        mock_kill.assert_any_call(124, signal.SIGKILL)
        # Should NOT have killed 123 or 125
        with pytest.raises(AssertionError):
            mock_kill.assert_any_call(123, signal.SIGKILL)
        with pytest.raises(AssertionError):
            mock_kill.assert_any_call(125, signal.SIGKILL)

@patch('src.app.get_config')
def test_background_session_preloader(mock_get_config):
    mock_get_config.return_value = {
        'HOSTS': [{'label': 'local', 'type': 'local'}]
    }
    
    with patch('src.app.fetch_sessions_for_host') as mock_fetch, \
         patch('src.app.socketio.sleep', side_effect=[None, Exception("Stop loop")]):
        
        mock_fetch.return_value = {"output": "some sessions", "error": None}
        
        try:
            background_session_preloader()
        except Exception as e:
            assert str(e) == "Stop loop"
            
        assert 'local:local:' in session_results_cache
        assert session_results_cache['local:local:']['output'] == "some sessions"

def test_pty_restart_basic(mock_socketio, mock_pty):
    from src.app import app
    # This tests the branch where a new PTY is created
    mock_pty.return_value = (0, 10) # child_pid=0, fd=10
    
    with app.test_request_context('/'):
        with patch('src.app.get_config_paths') as mock_paths, \
             patch('os.chdir'), \
             patch('os.execv'), \
             patch('os._exit'):
            
            mock_paths.return_value = ("/data", "/data/config.json", "/data/.ssh")
            
            # Trigger restart (child branch)
            pty_restart({'tab_id': 'tab1', 'sid': 'test-sid'})

    # Test parent branch
    mock_pty.return_value = (999, 10) # child_pid=999, fd=10
    with app.test_request_context('/'):
        with patch('src.app.set_winsize'):
            pty_restart({'tab_id': 'tab2', 'rows': 24, 'cols': 80, 'sid': 'test-sid'})
            
            from src.app import session_manager
            session = session_manager.get_session('tab2')
            assert session is not None
            assert session.pid == 999
