import re

with open("src/app.py", "r") as f:
    content = f.read()

# Extract handlers
start_idx = content.find("def register_socketio_handlers(app):")
end_idx = content.find("def register_blueprints(app_instance):")

if start_idx != -1 and end_idx != -1:
    handlers = content[start_idx:end_idx]

    # We will write these to src/gateways/terminal_socket.py
    # and remove them from src/app.py

    new_content = content[:start_idx] + content[end_idx:]
    with open("src/app.py", "w") as f:
        f.write(new_content)

    with open("src/gateways/terminal_socket.py", "w") as f:
        # imports needed for the handlers
        imports = """import logging
from flask import request as socket_request, session, current_app
from flask_wtf.csrf import validate_csrf, ValidationError
from flask_socketio import ConnectionRefusedError, join_room

from src.extensions import socketio
from src.config import env_config
from src.session_manager import session_manager
from src.shared_state import active_fake_sockets, active_fake_sockets_lock

logger = logging.getLogger(__name__)

"""
        f.write(imports + handlers)
