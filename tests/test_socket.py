import pytest
from unittest.mock import patch, MagicMock
from src.app import app, pty_input, pty_resize, handle_connect, handle_disconnect, session_manager, Session

def test_pty_input_handling():
    with app.test_request_context('/'):
        with patch('src.app.request') as mock_req, \
             patch('os.write') as mock_write:
            mock_req.sid = 'sid1'
            session = Session('tab1', 10, 123, 'admin')
            session_manager.add_session(session)
            session_manager.reclaim_session('tab1', 'sid1', 'admin')
            
            pty_input({'input': 'hello'})
            mock_write.assert_called_with(10, b'hello')

def test_pty_resize_handling():
    with app.test_request_context('/'):
        with patch('src.app.request') as mock_req, \
             patch('src.app.set_winsize') as mock_resize:
            mock_req.sid = 'sid1'
            session = Session('tab1', 10, 123, 'admin')
            session_manager.add_session(session)
            session_manager.reclaim_session('tab1', 'sid1', 'admin')
            
            pty_resize({'rows': 24, 'cols': 80})
            mock_resize.assert_called_with(10, 24, 80)

def test_connect_disconnect_logic():
    with app.test_request_context('/'):
        with patch('src.app.request') as mock_req:
            mock_req.sid = 'sid_new'
            handle_connect()
            # Just verify it doesn't crash
            
            session = Session('tab_new', 10, 123, 'admin')
            session_manager.add_session(session)
            session_manager.reclaim_session('tab_new', 'sid_new', 'admin')
            
            handle_disconnect()
            # Verify cleanup
            assert 'sid_new' not in session_manager.sid_to_tabid
            assert session_manager.get_session('tab_new', 'admin').orphaned_at is not None
