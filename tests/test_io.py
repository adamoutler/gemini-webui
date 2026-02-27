import pytest
from unittest.mock import MagicMock, patch
import os
from src.app import read_and_forward_pty_output, session_manager, Session

def test_read_and_forward_pty_output_basic(test_data_dir):
    # Setup state
    decoder_mock = MagicMock()
    decoder_mock.decode.return_value = "hello world"
    
    session = Session("tab1", 10, 123, "admin")
    session.decoder = decoder_mock
    session_manager.add_session(session)
    session_manager.reclaim_session("tab1", "sid1", "admin")
    
    with patch('select.select') as mock_select, \
         patch('os.read') as mock_read, \
         patch('src.app.socketio') as mock_sio:
        
        # 1. Simulate data ready
        mock_select.return_value = ([10], [], [])
        mock_read.return_value = b"hello world"
        
        # We need to escape the loop
        mock_sio.sleep.side_effect = [None, Exception("Stop")]
        
        try:
            read_and_forward_pty_output()
        except Exception as e:
            assert str(e) == "Stop"
            
        mock_read.assert_called_with(10, 20480)
        mock_sio.emit.assert_called_with('pty-output', {'output': 'hello world'}, room='sid1')
        assert "hello world" in session.buffer

def test_read_and_forward_pty_output_error():
    session = Session("tab_err", 11, 124, "admin")
    session_manager.add_session(session)
    
    with patch('select.select') as mock_select, \
         patch('os.read', side_effect=OSError("Read error")), \
         patch('src.app.socketio') as mock_sio:
        
        mock_select.return_value = ([11], [], [])
        mock_sio.sleep.side_effect = [None, Exception("Stop")]
        
        try:
            read_and_forward_pty_output()
        except Exception as e:
            assert str(e) == "Stop"
            
        # PTY should be removed on error
        assert 'tab_err' not in session_manager.sessions
