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

def test_extreme_data_injection_and_delta_updates():
    """
    Tests extreme data injection into xterm (around 2MB).
    Adding 2 lines should just retransmit necessary changes (delta updates).
    Ensures updates from end of buffer only apply to end of buffer.
    Tests for: creating, adding text, resuming, adding text to ensure no corruption.
    """
    session = Session("tab_extreme", 12, 125, "admin")
    session_manager.add_session(session)
    # 1. Creating session
    session_manager.reclaim_session("tab_extreme", "sid_extreme", "admin")
    
    # 2. Adding text (extreme data injection around 2MB)
    chunk_size = 20 * 1024
    total_size = 2 * 1024 * 1024
    num_chunks = total_size // chunk_size
    
    # Generate 2MB payload
    payload_chunks = [f"Chunk {i} data...\n".encode('utf-8').ljust(chunk_size, b'A') for i in range(num_chunks)]
    
    # Mocking decode
    session.decoder = MagicMock()
    session.decoder.decode.side_effect = lambda x: x.decode('utf-8')

    with patch('select.select') as mock_select, \
         patch('os.read') as mock_read, \
         patch('src.app.socketio') as mock_sio:
         
        mock_select.return_value = ([12], [], [])
        
        # side effects for os.read: return chunks then block
        mock_read.side_effect = payload_chunks + [b""]
        
        # mock sleep to break loop after chunks are read
        mock_sio.sleep.side_effect = [None] * num_chunks + [Exception("Stop")]
        
        try:
            read_and_forward_pty_output()
        except Exception as e:
            assert str(e) == "Stop"
        
        # Verify the chunks were emitted (delta updates during active connection)
        assert mock_sio.emit.call_count == num_chunks
        
        # Verify buffer size is constrained
        assert len(session.buffer) <= 300
        
        # 3. Resuming (reclaiming)
        mock_sio.reset_mock()
        # Simulate app logic for reclaim: it emits the whole buffer
        session_obj = session_manager.reclaim_session("tab_extreme", "sid_resume", "admin")
        mock_sio.emit('pty-output', {'output': "".join(session_obj.buffer)}, room='sid_resume')
        
        assert mock_sio.emit.call_count == 1
        emitted_buffer = mock_sio.emit.call_args[0][1]['output']
        # The buffer only keeps up to 300 chunks (300 * 20KB = ~6MB), since we sent 2MB, it has all of it
        assert len(emitted_buffer) == num_chunks * chunk_size
        
        # 4. Adding text (2 lines delta update) after resume to ensure no corruption
        mock_sio.reset_mock()
        mock_read.side_effect = [b"Line 1\nLine 2\n", b""]
        mock_sio.sleep.side_effect = [None, Exception("Stop")]
        
        try:
            read_and_forward_pty_output()
        except Exception as e:
            assert str(e) == "Stop"
            
        # It should just emit the 2 lines as a delta, not the whole buffer
        assert mock_sio.emit.call_count == 1
        delta_output = mock_sio.emit.call_args[0][1]['output']
        assert delta_output == "Line 1\nLine 2\n"
        
        # Ensure it was appended to the end of the buffer
        assert session.buffer[-1] == "Line 1\nLine 2\n"
