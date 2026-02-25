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
    # Mock some ptys
    from src.app import persistent_ptys, orphaned_ptys
    import time
    
    # 1. Active PTY
    persistent_ptys['active'] = {'pid': 123, 'fd': 4, 'decoder': MagicMock()}
    
    # 2. Orphaned PTY (old)
    persistent_ptys['old_orphan'] = {'pid': 124, 'fd': 5, 'decoder': MagicMock()}
    orphaned_ptys['old_orphan'] = time.time() - 100 # 100s ago
    
    # 3. Orphaned PTY (new)
    persistent_ptys['new_orphan'] = {'pid': 125, 'fd': 6, 'decoder': MagicMock()}
    orphaned_ptys['new_orphan'] = time.time() - 10 # 10s ago

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
            
            from src.app import persistent_ptys
            assert 'tab2' in persistent_ptys
            assert persistent_ptys['tab2']['pid'] == 999
