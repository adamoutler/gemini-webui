import logging
from flask import request as socket_request, session, current_app
from flask_wtf.csrf import validate_csrf, ValidationError
from flask_socketio import ConnectionRefusedError, join_room

from src.extensions import socketio
from src.config import env_config
from src.session_manager import session_manager

logger = logging.getLogger(__name__)

# We need access to these for the handlers
from src.process_manager import build_terminal_command, fetch_sessions_for_host
import threading
from src.routes.terminal import _get_gemini_sessions_impl

abandoned_pids = set()
abandoned_pids_lock = threading.Lock()
active_fake_sockets = {}
active_fake_sockets_lock = threading.Lock()

# I will extract all the socketio handlers here.
