import os
import shlex
import subprocess
from flask import jsonify, request
from flask.views import MethodView
from marshmallow import Schema, fields
from flask_smorest import Blueprint, Api

from src.app import get_config, get_config_paths, logger, GEMINI_BIN, api_key_required
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
        required=True, description="The label of the host to run the command on."
    )
    prompt = fields.String(
        required=True, description="The prompt/command to pass to Gemini."
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
        env_vars = host.get("env_vars")

        cmd = []
        if ssh_target:
            if not validate_ssh_target(ssh_target):
                return (
                    jsonify(
                        {"status": "error", "message": "Invalid SSH target format"}
                    ),
                    400,
                )

            remote_prefix = get_remote_command_prefix(
                ssh_dir, GEMINI_BIN, env_vars=env_vars
            )
            remote_cmd = (
                f"{remote_prefix} {shlex.quote(GEMINI_BIN)} {shlex.quote(prompt)}"
            )

            login_wrapped_cmd = f"bash -ilc {shlex.quote(remote_cmd)}"
            _, _, ssh_dir_path = get_config_paths()
            cmd = build_ssh_args(ssh_target, ssh_dir_path, control_master="no")

            clean_target = ssh_target
            if ":" in ssh_target:
                parts = ssh_target.rsplit(":", 1)
                if parts[1].isdigit():
                    clean_target = parts[0]
                    cmd.extend(["-p", parts[1]])

            cmd.extend(["--", clean_target, login_wrapped_cmd])
        else:
            data_dir = env_config.DATA_DIR
            work_dir = os.path.join(data_dir, "workspace")
            if os.path.exists(work_dir):
                cmd = [
                    "/bin/sh",
                    "-c",
                    f'cd {shlex.quote(work_dir)} && exec {shlex.quote(GEMINI_BIN)} "$1"',
                    "--",
                    prompt,
                ]
            else:
                cmd = [
                    "/bin/sh",
                    "-c",
                    f'exec {shlex.quote(GEMINI_BIN)} "$1"',
                    "--",
                    prompt,
                ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Gemini command failed",
                            "stderr": result.stderr,
                            "stdout": result.stdout,
                        }
                    ),
                    500,
                )

            return jsonify(
                {
                    "status": "success",
                    "data": {"stdout": result.stdout, "stderr": result.stderr},
                }
            )
        except subprocess.TimeoutExpired:
            return (
                jsonify({"status": "error", "message": "Gemini command timed out"}),
                504,
            )
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return jsonify(
                {"status": "error", "message": "An internal error occurred"}
            ), 500


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

        _, _, ssh_dir_path = get_config_paths()
        result = fetch_sessions_for_host(host, ssh_dir_path, GEMINI_BIN)

        if "error" in result and result["error"]:
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
