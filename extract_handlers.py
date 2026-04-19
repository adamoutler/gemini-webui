import os

with open("src/app.py", "r") as f:
    app_code = f.read()

# Find bounds for chunk 1
chunk1_start = app_code.find('@socketio.on("connect")')
chunk1_end = app_code.find("@app.before_request\n")

# Find bounds for chunk 2
chunk2_start = app_code.find("def set_winsize(fd, row, col, xpix=0, ypix=0):")
chunk2_end = app_code.find("def register_blueprints(app_instance):")

if chunk1_start == -1 or chunk1_end == -1 or chunk2_start == -1 or chunk2_end == -1:
    print("Could not find all boundaries")
    exit(1)

chunk1 = app_code[chunk1_start:chunk1_end]
chunk2 = app_code[chunk2_start:chunk2_end]

# Remove chunks from app.py
new_app_code = (
    app_code[:chunk1_start]
    + "import src.gateways.terminal_socket\n\n\n"
    + app_code[chunk1_end:chunk2_start]
    + app_code[chunk2_end:]
)

with open("src/app.py", "w") as f:
    f.write(new_app_code)

# Prepare imports for terminal_socket.py
imports = """import os
import struct
import fcntl
import termios
import select
import errno
import pty
import time
import threading
import shlex
import logging

from flask import request, session, current_app
from flask_wtf.csrf import validate_csrf, ValidationError
from flask_socketio import ConnectionRefusedError, join_room

from src.extensions import socketio
from src.config import env_config, get_config, get_config_paths
from src.services.session_store import session_manager
from src.shared_state import active_fake_sockets, active_fake_sockets_lock, ephemeral_sessions
from src.services.process_engine import fetch_sessions_for_host, build_terminal_command
from src.app import kill_and_reap, add_managed_pty, IDENTIFICATION_REGEX, app
from src.models.session import Session

logger = logging.getLogger(__name__)
GEMINI_BIN = "gemini"

"""

with open("src/gateways/terminal_socket.py", "w") as f:
    f.write(imports + chunk1 + chunk2)

print("Extraction successful.")
