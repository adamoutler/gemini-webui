import pytest
from unittest.mock import patch
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
        # Mock ORPHANED_SESSION_TTL to 60 for testing
        from src.app import app
        app.config['ORPHANED_SESSION_TTL'] = 60
        
        cleanup_orphaned_ptys()
        
        # Only old_orphan should be killed
        assert mock_kill.call_count == 1
        mock_kill.assert_called_with(124, 9) # SIGKILL is 9
        
        # Verify it was removed from the session manager
        assert session_manager.get_session('old_orphan') is None
        # Verify active and new_orphan still exist
        assert session_manager.get_session('active') is not None
        assert session_manager.get_session('new_orphan') is not None

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
             patch('src.app.get_config') as mock_get_config, \
             patch('shutil.which', return_value=None), \
             patch('os.chdir'), \
             patch('os.execv'), \
             patch('os.execvp') as mock_execvp, \
             patch('os._exit'), \
             patch('src.app.build_terminal_command', return_value=['bash']) as mock_build_cmd:            
            mock_paths.return_value = ("/data", "/data/config.json", "/data/.ssh")
            mock_get_config.return_value = {
                'HOSTS': [{'target': 'test@host', 'env_vars': {'MY_VAR': '123'}}]
            }
            
            # Trigger restart (child branch)
            pty_restart({'tab_id': 'tab1', 'sid': 'test-sid', 'ssh_target': 'test@host', 'ssh_dir': '/remote/dir', 'resume': True})
            
            mock_execvp.assert_called_once_with('bash', ['bash'])
            import os
            from src.app import GEMINI_BIN
            mock_build_cmd.assert_called_once_with('test@host', '/remote/dir', True, '/data/.ssh', GEMINI_BIN, env_vars={'MY_VAR': '123'})
            assert os.environ.get('TERM') == 'xterm-256color'
            assert os.environ.get('COLORTERM') == 'truecolor'
            assert os.environ.get('FORCE_COLOR') == '3'

    # Test parent branch
    mock_pty.return_value = (999, 10) # child_pid=999, fd=10
    with app.test_request_context('/'):
        with patch('src.app.set_winsize') as mock_set_winsize:
            pty_restart({'tab_id': 'tab2', 'rows': 24, 'cols': 80, 'sid': 'test-sid', 'ssh_target': 'test@host', 'ssh_dir': '/home/test'})
            
            from src.app import session_manager
            session = session_manager.get_session('tab2')
            assert session is not None
            assert session.pid == 999
            assert session.fd == 10
            assert session.tab_id == 'tab2'
            assert session.ssh_target == 'test@host'
            assert session.ssh_dir == '/home/test'
            assert session.resume is True
            mock_set_winsize.assert_called_with(10, 24, 80)

            # Test default rows/cols
            pty_restart({'tab_id': 'tab3', 'sid': 'test-sid3'})
            session3 = session_manager.get_session('tab3')
            assert session3 is not None
            assert session3.pid == 999
            assert session3.fd == 10
            assert session3.tab_id == 'tab3'
            assert session3.ssh_target is None
            assert session3.ssh_dir is None
            assert session3.resume is True
            mock_set_winsize.assert_called_with(10, 24, 80)

def test_pty_restart_lru_eviction(mock_socketio, mock_pty):
    from src.app import app, session_manager, Session
    import time
    
    # child_pid=999, fd=10
    mock_pty.return_value = (999, 10)
    
    # Fill up session manager with 10 sessions, each with a different last_seen
    session_manager.sessions.clear()
    session_manager.tabid_to_sid.clear()
    now = time.time()
    for i in range(10):
        tab_id = f'tab_{i}'
        s = Session(tab_id, i+10, 1000+i, 'admin')
        s.last_seen = now - (100 - i) # tab_0 is oldest, tab_9 is newest
        session_manager.add_session(s)
        session_manager.tabid_to_sid[tab_id] = f'sid_{i}'
    
    with app.test_request_context('/'):
        with patch('os.kill') as mock_kill, \
             patch('os.waitpid') as mock_wait, \
             patch('src.app.set_winsize'):
            
            # Attempt to start the 11th session
            pty_restart({'tab_id': 'tab_new', 'sid': 'sid_new'})
            
            # Verify LRU: tab_0 (PID 1000) should have been killed
            mock_kill.assert_any_call(1000, signal.SIGKILL)
            
            # Verify tab_0 was removed
            assert session_manager.get_session('tab_0') is None
            # Verify tab_new was added
            assert session_manager.get_session('tab_new') is not None
            # Verify session count remains 10
            assert len(session_manager.sessions) == 10
            
            # Verify notification was sent to evicted tab's SID (sid_0)
            mock_socketio.emit.assert_any_call('pty-output', {'output': '\r\n\x1b[2m[Warning: This session was evicted to make room for a new one.]\x1b[0m\r\n'}, room='sid_0')
