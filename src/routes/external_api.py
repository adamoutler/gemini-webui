import os
import shlex
import subprocess
from flask import jsonify, request
from flask.views import MethodView
from marshmallow import Schema, fields
from flask_smorest import Blueprint, Api

from src.config import get_config, get_config_paths
import logging

logger = logging.getLogger(__name__)
from src.config import env_config

GEMINI_BIN = env_config.GEMINI_BIN
from src.auth import api_key_required
from src.services.process_engine import (
    fetch_sessions_for_host,
    validate_ssh_target,
    get_remote_command_prefix,
    build_ssh_args,
)
from src.config import env_config

external_api_bp = Blueprint(
    "external_api",
    __name__,
    description="Operations for Gemini WebUI programmatic access",
)


class SessionCreateSchema(Schema):
    host_id = fields.String(
        required=True,
        metadata={"description": "The label of the host to run the command on."},
    )
    prompt = fields.String(
        required=True, metadata={"description": "The prompt/command to pass to Gemini."}
    )


class SessionResponseSchema(Schema):
    status = fields.String()
    data = fields.Dict(keys=fields.String(), values=fields.String())
    message = fields.String()


class HostStateResponseSchema(Schema):
    status = fields.String()
    data = fields.Dict(keys=fields.String(), values=fields.Raw())
    message = fields.String()


@external_api_bp.route("/v1/sessions/create")
class SessionCreate(MethodView):
    @external_api_bp.arguments(SessionCreateSchema)
    @external_api_bp.response(200, SessionResponseSchema)
    @api_key_required
    def post(self, data):
        """Create a new session with a given prompt and return the output."""
        host_id = data.get("host_id")
        prompt = data.get("prompt")

        conf = get_config()
        hosts = conf.get("HOSTS", [])
        host = next((h for h in hosts if h["label"] == host_id), None)

        if not host:
            return (
                jsonify({"status": "error", "message": f"Host '{host_id}' not found"}),
                404,
            )

        ssh_target = host.get("target")
        ssh_dir = host.get("dir")

        from src.services.terminal_service import TerminalService

        result, status_code = TerminalService.execute_command_sync(
            ssh_target, ssh_dir, prompt
        )
        return jsonify(result), status_code


@external_api_bp.route("/v1/hosts/<host_id>/states")
class HostStates(MethodView):
    @external_api_bp.response(200, HostStateResponseSchema)
    @api_key_required
    def get(self, host_id):
        """Retrieve the current states (sessions) of a given host."""
        conf = get_config()
        hosts = conf.get("HOSTS", [])
        host = next((h for h in hosts if h["label"] == host_id), None)

        if not host:
            return (
                jsonify({"status": "error", "message": f"Host '{host_id}' not found"}),
                404,
            )

        ssh_target = host.get("target")
        ssh_dir = host.get("dir")
        cache_key = f"{'ssh' if ssh_target else 'local'}:{ssh_target or 'local'}:{ssh_dir or ''}"

        from src.services.session_poller import session_poller_manager
        from src.shared_state import session_results_cache, session_results_cache_lock

        session_poller_manager.update_frontend_activity()
        with session_results_cache_lock:
            result = session_results_cache.get(cache_key, {})

        if result.get("error"):
            return jsonify({"status": "error", "message": result["error"]}), 500

        return jsonify(
            {
                "status": "success",
                "data": {
                    "sessions": result.get("output", ""),
                    "timestamp": result.get("timestamp"),
                },
            }
        )


@external_api_bp.route("/v1/hosts/<host_id>/states/wait/<wait_time>")
class HostStateWait(MethodView):
    @external_api_bp.response(200, HostStateResponseSchema)
    @api_key_required
    def get(self, host_id, wait_time):
        """Wait for sessions of a given host to be ready."""
        import time

        conf = get_config()
        hosts = conf.get("HOSTS", [])
        host = next((h for h in hosts if h["label"] == host_id), None)

        if not host:
            return jsonify(
                {"status": "error", "message": f"Host '{host_id}' not found"}
            ), 404

        # Parse wait_time (eg. 10s, 5m, 2h)
        seconds = 0
        if wait_time.endswith("s"):
            seconds = int(wait_time[:-1])
        elif wait_time.endswith("m"):
            seconds = int(wait_time[:-1]) * 60
        elif wait_time.endswith("h"):
            seconds = int(wait_time[:-1]) * 3600
        else:
            try:
                seconds = int(wait_time)
            except ValueError:
                return jsonify(
                    {"status": "error", "message": "Invalid time format"}
                ), 400

        from src.services.session_store import session_manager

        start_time = time.time()
        while time.time() - start_time < seconds:
            sessions = session_manager.get_all_sessions()
            all_ready = True
            for s in sessions:
                # Simple heuristic: if title doesn't contain "Working" or "✋", it's ready
                if s.title and ("Working" in s.title or "✋" in s.title):
                    all_ready = False
                    break

            if all_ready and sessions:  # Ensure there are sessions to wait for
                return jsonify({"status": "success", "message": "ready"})

            time.sleep(2)

        return jsonify({"status": "error", "message": "timeout"}), 504
