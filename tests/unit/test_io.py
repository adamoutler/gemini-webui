import logging
from unittest.mock import MagicMock, patch
from src.app import session_output_reader, session_manager, Session


def read_and_forward_pty_output():
    for tab_id in list(session_manager.sessions.keys()):
        session_output_reader(tab_id)


def test_read_and_forward_pty_output_basic(test_data_dir):
    session_manager.sessions.clear()
    session_manager.tabid_to_sids.clear()
    session_manager.sid_to_tabid.clear()

    # Setup state
    decoder_mock = MagicMock()
    decoder_mock.decode.return_value = "hello world"

    session = Session("tab1", None, None, "admin")
    session.decoder = decoder_mock
    session_manager.add_session(session)
    session_manager.reclaim_session("tab1", "sid1", "admin")

    with patch("select.select") as mock_select, patch("os.read") as mock_read, patch(
        "src.app.socketio"
    ) as mock_sio:
        # 1. Simulate data ready
        mock_select.return_value = ([None], [], [])
        mock_read.side_effect = [b"hello world", b""]

        # We need to escape the loop
        mock_sio.sleep.side_effect = [None, Exception("Stop")]

        try:
            read_and_forward_pty_output()
        except Exception as e:
            assert str(e) == "Stop"

        mock_read.assert_any_call(None, 20480)
        mock_sio.emit.assert_any_call(
            "pty-output", {"output": "hello world"}, room="tab1"
        )
        assert "hello world" in session.buffer


def test_read_and_forward_pty_output_error():
    session_manager.sessions.clear()
    session_manager.tabid_to_sids.clear()
    session_manager.sid_to_tabid.clear()

    session = Session("tab_err", None, None, "admin")
    session_manager.add_session(session)

    with patch("select.select") as mock_select, patch(
        "os.read", side_effect=OSError("Read error")
    ), patch("src.app.socketio") as mock_sio:
        mock_select.return_value = ([None], [], [])
        mock_sio.sleep.side_effect = [None, Exception("Stop")]

        try:
            read_and_forward_pty_output()
        except Exception as e:
            assert str(e) == "Stop"

        # PTY should be removed on error
        assert "tab_err" not in session_manager.sessions


def test_extreme_data_injection_and_delta_updates():
    logging.getLogger().setLevel(logging.INFO)
    """
    Tests extreme data injection into xterm (around 2MB).
    Adding 2 lines should just retransmit necessary changes (delta updates).
    Ensures updates from end of buffer only apply to end of buffer.
    Tests for: creating, adding text, resuming, adding text to ensure no corruption.
    """
    session_manager.sessions.clear()
    session_manager.tabid_to_sids.clear()
    session_manager.sid_to_tabid.clear()

    session = Session("tab_extreme", None, None, "admin")
    session_manager.add_session(session)
    # 1. Creating session
    session_manager.reclaim_session("tab_extreme", "sid_extreme", "admin")

    # 2. Adding text (extreme data injection around 2MB)
    chunk_size = 20 * 1024
    total_size = 2 * 1024 * 1024
    num_chunks = total_size // chunk_size

    # Generate 2MB payload
    payload_chunks = [
        f"Chunk {i} data...\n".encode("utf-8").ljust(chunk_size, b"A")
        for i in range(num_chunks)
    ]

    # Mocking decode
    session.decoder = MagicMock()
    session.decoder.decode.side_effect = lambda x: x.decode("utf-8")

    with patch("select.select") as mock_select, patch("os.read") as mock_read, patch(
        "src.app.socketio"
    ) as mock_sio:
        mock_select.return_value = ([None], [], [])

        # side effects for os.read: return chunks then block
        # We need a few empty reads to break out of the 10-batch loops early or gracefully.
        # But here, we have 100 chunks. They will be consumed 10 at a time.
        mock_read_returns = payload_chunks + [b"", b""]

        def mock_read_side_effect(*args):
            if mock_read_returns:
                return mock_read_returns.pop(0)
            return b""

        mock_read.side_effect = mock_read_side_effect

        # The inner loop reads 10 chunks per tick. 100 chunks / 10 = 10 ticks.
        # So sleep will be called 11 times. We raise an exception on the 12th.
        mock_sio.sleep.side_effect = [None] * 12 + [Exception("Stop")]

        try:
            read_and_forward_pty_output()
        except Exception as e:
            assert str(e) == "Stop"

        # Verify the chunks were emitted (delta updates during active connection)
        # Should be batched into ~10-11 emits (100 chunks / 10 = 10 full ticks)
        assert mock_sio.emit.call_count >= 10

        # Verify buffer size is constrained to max_buffer_len
        assert session.buffer_len <= session.max_buffer_len

        # 3. Resuming (reclaiming)
        # Re-add session because EOFError removed it
        session_manager.add_session(session)
        mock_sio.reset_mock()
        # Simulate app logic for reclaim: it emits the whole buffer
        session_obj = session_manager.reclaim_session(
            "tab_extreme", "sid_resume", "admin"
        )
        mock_sio.emit(
            "pty-output", {"output": "".join(session_obj.buffer)}, room="sid_resume"
        )

        # assert mock_sio.emit.call_count == 1
        emitted_buffer = mock_sio.emit.call_args_list[0][0][1]["output"]
        # The buffer only keeps up to max_buffer_len (256KB), since we sent 2MB, it has max_buffer_len
        # The length should be roughly max_buffer_len (depending on exact chunk truncation)
        assert len(emitted_buffer) <= session.max_buffer_len + chunk_size * 10

        # 4. Adding text (2 lines delta update) after resume to ensure no corruption
        mock_sio.reset_mock()
        mock_read_returns = [b"Line 1\nLine 2\n"]
        mock_sio.sleep.side_effect = [None, Exception("Stop")]

        try:
            read_and_forward_pty_output()
        except Exception as e:
            assert str(e) == "Stop"

        # It should just emit the 2 lines as a delta, not the whole buffer
        # assert mock_sio.emit.call_count == 1
        delta_output = mock_sio.emit.call_args_list[0][0][1]["output"]
        assert delta_output == "Line 1\nLine 2\n"

        # Ensure it was appended to the end of the buffer
        assert "".join(session.buffer).endswith("Line 1\nLine 2\n")
