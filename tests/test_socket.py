import pytest
from unittest.mock import patch, MagicMock
from src.app import app, pty_input, pty_resize, handle_connect, handle_disconnect, sid_to_tabid, tabid_to_sid, persistent_ptys

def test_pty_input_handling():
    with app.test_request_context('/'):
        with patch('src.app.request') as mock_req, \
             patch('os.write') as mock_write:
            mock_req.sid = 'sid1'
            sid_to_tabid['sid1'] = 'tab1'
            persistent_ptys['tab1'] = {'fd': 10, 'pid': 123}
            
            pty_input({'input': 'hello'})
            mock_write.assert_called_with(10, b'hello')

def test_pty_resize_handling():
    with app.test_request_context('/'):
        with patch('src.app.request') as mock_req, \
             patch('src.app.set_winsize') as mock_resize:
            mock_req.sid = 'sid1'
            sid_to_tabid['sid1'] = 'tab1'
            persistent_ptys['tab1'] = {'fd': 10, 'pid': 123}
            
            pty_resize({'rows': 24, 'cols': 80})
            mock_resize.assert_called_with(10, 24, 80)

def test_connect_disconnect_logic():
    with app.test_request_context('/'):
        with patch('src.app.request') as mock_req:
            mock_req.sid = 'sid_new'
            handle_connect()
            # Just verify it doesn't crash
            
            sid_to_tabid['sid_new'] = 'tab_new'
            tabid_to_sid['tab_new'] = 'sid_new'
            handle_disconnect()
            # Verify cleanup
            assert 'sid_new' not in sid_to_tabid
            assert 'tab_new' not in tabid_to_sid
