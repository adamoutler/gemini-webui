import pytest
from unittest.mock import patch
from src.app import session_output_reader, session_manager, Session


def read_and_forward_pty_output():
    for tab_id in list(session_manager.sessions.keys()):
        session_output_reader(tab_id)


# Define a suite of bad/adversarial payloads
BAD_PAYLOADS = [
    b"\x1b]0;" + b"A" * 100000 + b"\x07",  # Massive OSC
    b"\x1b[?25h" * 1000,  # Spammy normal sequences
    b"\x1b[",  # Incomplete sequence
    b"\x1b[20;",  # Incomplete sequence
    b"\x1b[?62;c",  # Identification response
    b"\xff\xfe\xfd",  # Invalid UTF-8
    b"\x1b[20;20H\x1b[?25l" * 500,  # Cursor moving spam
    b"\x00" * 10000,  # Null bytes
    b"\x1b]8;;http://malicious.com\x1b\\Click here\x1b]8;;\x1b\\",  # OSC 8 hyperlink
    b"\x1b[38;5;255m" * 1000,  # 256 color spam
    b"\x1b[38;2;255;255;255m" * 1000,  # Truecolor spam
    b"\x1b[?1000h\x1b[?1002h\x1b[?1006h\x1b[?1015h",  # Mouse tracking spam
    b"\x1b[c",  # Identification without numbers (to test regex edge case)
    b"\x1b[?c",
    b"\x1b[" + b"1;" * 5000 + b"c",  # Massive identification response
]


@pytest.mark.parametrize("payload", BAD_PAYLOADS)
def test_ansi_injection(payload):
    # Setup state
    session_manager.sessions.clear()
    session_manager.sid_to_tabid.clear()
    session_manager.tabid_to_sids.clear()

    session = Session("tab_ansi", None, None, "admin")
    session_manager.add_session(session)
    session_manager.reclaim_session("tab_ansi", "sid_ansi", "admin")

    with patch("select.select") as mock_select, patch("os.read") as mock_read, patch(
        "src.app.socketio"
    ) as mock_sio:
        mock_select.return_value = ([None], [], [])

        read_returns = [payload, b""]

        def mock_read_side_effect(*args):
            if read_returns:
                return read_returns.pop(0)
            return b""

        mock_read.side_effect = mock_read_side_effect

        read_and_forward_pty_output()

        session_manager.remove_session("tab_ansi", "admin")


def test_ansi_injection_mixed_chunks():
    session_manager.sessions.clear()
    session_manager.sid_to_tabid.clear()
    session_manager.tabid_to_sids.clear()

    session = Session("tab_ansi_mix", None, None, "admin")
    session_manager.add_session(session)
    session_manager.reclaim_session("tab_ansi_mix", "sid_ansi_mix", "admin")

    massive_payload = b"\x1b]0;" + b"A" * 100000 + b"\x07"
    chunks = [
        massive_payload[i : i + 1024] for i in range(0, len(massive_payload), 1024)
    ]

    with patch("select.select") as mock_select, patch("os.read") as mock_read, patch(
        "src.app.socketio"
    ) as mock_sio:
        mock_select.return_value = ([None], [], [])

        read_returns = chunks + [b""]

        def mock_read_side_effect(*args):
            if read_returns:
                return read_returns.pop(0)
            return b""

        mock_read.side_effect = mock_read_side_effect

        iterations = (len(chunks) // 10) + 5

        read_and_forward_pty_output()

        session_manager.remove_session("tab_ansi_mix", "admin")
