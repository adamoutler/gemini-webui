import re

with open("src/app.py", "r") as f:
    content = f.read()

# Define the boundaries
start_marker = '@socketio.on("connect")'
end_marker = "def register_blueprints(app_instance):"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print("Markers not found.")
    exit(1)

handlers_content = content[start_idx:end_idx]

# We need to remove the handlers from app.py
new_app_content = content[:start_idx] + content[end_idx:]

# We need to add the import to app.py. We can add it just before register_blueprints is called or inside init_app.
init_app_idx = new_app_content.find("def init_app():")
import_stmt = "    import src.gateways.terminal_socket\n"
# insert after def init_app():
insert_idx = new_app_content.find(":", init_app_idx) + 1
new_app_content = (
    new_app_content[:insert_idx] + "\n" + import_stmt + new_app_content[insert_idx:]
)

with open("src/app.py", "w") as f:
    f.write(new_app_content)

# Now create terminal_socket.py
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
from src.services.process_engine import fetch_sessions_for_host, build_terminal_command, kill_and_reap, add_managed_pty
from src.models.session import Session, IDENTIFICATION_REGEX

logger = logging.getLogger(__name__)
GEMINI_BIN = "gemini"

"""

with open("src/gateways/terminal_socket.py", "w") as f:
    f.write(imports + handlers_content)

print("Extraction complete.")
