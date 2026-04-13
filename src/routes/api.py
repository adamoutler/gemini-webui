import os
import subprocess
import tempfile
import uuid
import shutil
import json
import zipfile
import shlex
import logging
import secrets
import hashlib
import datetime
from functools import wraps
from flask import Blueprint, jsonify, request, send_file, send_from_directory
from werkzeug.utils import secure_filename
from flask_wtf.csrf import generate_csrf

from src.config import env_config
from src.app import get_config, get_config_paths, authenticated_only, logger
from src.process_manager import (
    validate_ssh_target,
    build_ssh_args,
    build_terminal_command,
)
from src.session_manager import session_manager
from src.prompt_manager import prompt_manager

api_bp = Blueprint("api", __name__)


def bearer_token_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        token = auth_header[7:]
        hashed_token = hashlib.sha256(token.encode()).hexdigest()
        conf = get_config()
        if hashed_token not in conf.get("API_KEYS", []):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return wrapped


@api_bp.route("/api/config", methods=["GET"])
@authenticated_only
def get_current_config():
    conf = get_config()
    conf.pop("LDAP_BIND_PASS", None)
    conf.pop("ADMIN_PASS", None)
    conf.pop("API_KEYS", None)  # Don't leak hashes even to authenticated users
    return jsonify(conf)


@api_bp.route("/api/config", methods=["POST"])
@authenticated_only
def update_config():
    new_conf = request.json
    curr_conf = get_config()
    # Don't allow updating API_KEYS via this generic endpoint
    new_conf.pop("API_KEYS", None)
    curr_conf.update(new_conf)
    _, config_file, _ = get_config_paths()
    with open(config_file, "w") as f:
        json.dump(curr_conf, f, indent=4)
    return jsonify({"status": "success"})


@api_bp.route("/api/management/api-keys", methods=["GET"])
@authenticated_only
def list_api_keys():
    # Only return metadata, not hashes
    conf = get_config()
    key_metadata = conf.get("API_KEYS_METADATA", [])
    return jsonify(key_metadata)


@api_bp.route("/api/management/api-keys", methods=["POST"])
@authenticated_only
def create_api_key():
    new_key = secrets.token_hex(32)
    hashed_key = hashlib.sha256(new_key.encode()).hexdigest()
    note = request.json.get("note", "New Key")

    curr_conf = get_config()
    api_keys = curr_conf.get("API_KEYS", [])
    api_keys.append(hashed_key)
    curr_conf["API_KEYS"] = api_keys

    metadata = curr_conf.get("API_KEYS_METADATA", [])
    key_id = str(uuid.uuid4())[:8]
    metadata.append(
        {
            "id": key_id,
            "hash": hashed_key,
            "note": note,
            "created_at": str(datetime.datetime.now()),
        }
    )
    curr_conf["API_KEYS_METADATA"] = metadata

    _, config_file, _ = get_config_paths()
    with open(config_file, "w") as f:
        json.dump(curr_conf, f, indent=4)

    return jsonify({"status": "success", "key": new_key})


@api_bp.route("/api/management/api-keys/<hash_val>", methods=["DELETE"])
@authenticated_only
def delete_api_key(hash_val):
    curr_conf = get_config()
    api_keys = curr_conf.get("API_KEYS", [])
    metadata = curr_conf.get("API_KEYS_METADATA", [])

    if hash_val in api_keys:
        api_keys.remove(hash_val)
        curr_conf["API_KEYS"] = api_keys

        new_metadata = [m for m in metadata if m["hash"] != hash_val]
        curr_conf["API_KEYS_METADATA"] = new_metadata

        _, config_file, _ = get_config_paths()
        with open(config_file, "w") as f:
            json.dump(curr_conf, f, indent=4)
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Key not found"}), 404


@api_bp.route("/api/v1/sessions/create", methods=["POST"])
@bearer_token_required
def v1_create_session():
    data = request.json
    host_id = data.get("host_id")
    prompt = data.get("prompt")

    if not host_id or not prompt:
        return jsonify({"error": "Missing host_id or prompt"}), 400

    conf = get_config()
    if conf.get("host_id") != host_id:
        return jsonify({"error": "Invalid host_id for this server"}), 403

    # Use default local target for now, or extend to handle SSH targets if needed
    ssh_target = None
    ssh_dir = None
    resume = "new"
    tab_id = "v1-" + uuid.uuid4().hex[:8]

    _, _, ssh_dir_path = get_config_paths()
    cmd = build_terminal_command(
        ssh_target,
        ssh_dir,
        resume,
        ssh_dir_path,
        env_config.GEMINI_BIN,
    )

    # In a real scenario, we'd pipe the prompt to the session.
    # For this simplified implementation, we'll just run it once if possible.
    # But the requirement is to "execute prompt via Gemini CLI on the target host".

    # We can use subprocess to run the command directly and return output
    # or start a background session. The requirement says "Response: Success/Failure with stdout and stderr".
    # This implies a one-off execution.

    full_cmd = cmd + [prompt]
    try:
        result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=120)
        return jsonify(
            {
                "status": "success" if result.returncode == 0 else "failure",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        )
    except subprocess.TimeoutExpired:
        return jsonify({"status": "failure", "error": "Timeout expired"}), 504
    except Exception as e:
        return jsonify({"status": "failure", "error": str(e)}), 500


@api_bp.route("/api/v1/hosts/states", methods=["GET"])
@bearer_token_required
def v1_host_states():
    # Return current session status for this host
    sessions = session_manager.get_all_sessions()
    states = []
    for s in sessions:
        states.append(
            {
                "tab_id": s.tab_id,
                "title": s.title,
                "ssh_target": s.ssh_target,
                "last_seen": s.last_seen,
                "orphaned_at": s.orphaned_at,
            }
        )
    return jsonify({"host_id": get_config().get("host_id"), "sessions": states})


@api_bp.route("/api/v1/hosts/states/wait/<host_id>/<wait_time>", methods=["GET"])
@bearer_token_required
def v1_wait_for_ready(host_id, wait_time):
    conf = get_config()
    if conf.get("host_id") != host_id:
        return jsonify({"error": "Invalid host_id"}), 403

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
            return jsonify({"error": "Invalid time format"}), 400

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
            return jsonify({"status": "ready"})

        time.sleep(2)

    return jsonify({"status": "timeout"}), 504


@api_bp.route("/api/settings/export", methods=["GET"])
@authenticated_only
def export_settings():
    try:
        data_dir, _, _ = get_config_paths()
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, "settings")
        shutil.make_archive(zip_path, "zip", data_dir)
        return send_file(
            zip_path + ".zip",
            as_attachment=True,
            download_name="settings.gwui",
            mimetype="application/zip",
        )
    except Exception as e:
        logger.error(f"Failed to export settings: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/settings/import", methods=["POST"])
@authenticated_only
def import_settings():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if not (file.filename.endswith(".gwui") or file.filename.endswith(".zip")):
        return jsonify({"error": "Invalid file type. Must be .gwui or .zip"}), 400

    data_dir, _, _ = get_config_paths()
    try:
        temp_zip = os.path.join(tempfile.gettempdir(), f"import_{uuid.uuid4().hex}.zip")
        file.save(temp_zip)

        with zipfile.ZipFile(temp_zip, "r") as zip_ref:
            zip_ref.extractall(data_dir)

        os.remove(temp_zip)

        ssh_dir = os.path.join(data_dir, ".ssh")
        if os.path.exists(ssh_dir):
            os.chmod(ssh_dir, 0o700)
            for root, dirs, files in os.walk(ssh_dir):
                for d in dirs:
                    os.chmod(os.path.join(root, d), 0o700)
                for f in files:
                    os.chmod(os.path.join(root, f), 0o600)

        return jsonify({"success": True})
    except zipfile.BadZipFile:
        return jsonify({"error": "The uploaded file is not a valid zip archive"}), 400
    except Exception as e:
        logger.error(f"Failed to import settings: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/csrf-token", methods=["GET"])
def get_csrf_token_endpoint():
    token = generate_csrf()
    response = jsonify({"csrf_token": token})
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@api_bp.route("/api/csrf", methods=["GET"])
def get_csrf_token():
    return jsonify({"csrf_token": generate_csrf()})


@api_bp.route("/api/upload", methods=["POST"])
@authenticated_only
def upload_file():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "No selected file"}), 400

    original_filename = file.filename
    if "/" in original_filename or "\\" in original_filename:
        normalized_path = original_filename.replace("\\", "/")
        parts = [secure_filename(p) for p in normalized_path.split("/") if p]
        filename = "/".join(parts)
    else:
        filename = secure_filename(file.filename)

    if not filename:
        return jsonify({"status": "error", "message": "Invalid filename"}), 400

    workspace_dir = os.path.join(env_config.DATA_DIR, "workspace")
    base_path = os.path.abspath(workspace_dir)
    save_path = os.path.abspath(os.path.join(base_path, filename))

    if not save_path.startswith(base_path):
        return jsonify({"status": "error", "message": "Access denied"}), 403

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    file.save(save_path)

    ssh_target = request.form.get("ssh_target")
    if ssh_target:
        if not validate_ssh_target(ssh_target):
            return jsonify({"status": "error", "message": "Invalid SSH target"}), 400

        ssh_dir = request.form.get("ssh_dir")
        _, _, ssh_dir_path = get_config_paths()

        if not ssh_dir or ssh_dir == "~":
            remote_path = filename
        elif ssh_dir.startswith("~/"):
            remote_path = f"{ssh_dir[2:]}/{filename}"
        else:
            remote_path = os.path.join(ssh_dir, filename).replace("\\", "/")

        remote_dir = os.path.dirname(remote_path)
        port = None
        clean_target = ssh_target
        if ":" in ssh_target:
            parts = ssh_target.rsplit(":", 1)
            if parts[1].isdigit():
                clean_target = parts[0]
                port = parts[1]

        ssh_cmd_base = build_ssh_args(ssh_target, ssh_dir_path)
        if port:
            ssh_cmd_base.extend(["-p", port])

        scp_cmd_base = ["scp"] + build_ssh_args(ssh_target, ssh_dir_path)[1:]
        if port:
            scp_cmd_base.extend(["-P", port])

        if remote_dir:
            ssh_cmd = ssh_cmd_base + [
                "--",
                clean_target,
                f"mkdir -p {shlex.quote(remote_dir)}",
            ]
            res = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=15)
            if res.returncode != 0:
                return jsonify(
                    {
                        "status": "error",
                        "message": f"Failed to create remote directory: {res.stderr}",
                    }
                ), 500

        scp_cmd = scp_cmd_base + ["--", save_path, f"{clean_target}:{remote_path}"]
        try:
            result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return jsonify(
                    {"status": "error", "message": f"SCP failed: {result.stderr}"}
                ), 500

            verify_cmd = ssh_cmd_base + [
                "--",
                clean_target,
                f"ls {shlex.quote(remote_path)}",
            ]
            verify_res = subprocess.run(verify_cmd, capture_output=True, timeout=15)
            if verify_res.returncode != 0:
                return jsonify(
                    {
                        "status": "error",
                        "message": "SCP returned 0, but file verification failed on remote host.",
                    }
                ), 500

            path_cmd = ssh_cmd_base + [
                "--",
                clean_target,
                f"realpath {shlex.quote(remote_path)} 2>/dev/null || readlink -m {shlex.quote(remote_path)} 2>/dev/null || echo {shlex.quote(remote_path)}",
            ]
            path_res = subprocess.run(
                path_cmd, capture_output=True, text=True, timeout=15
            )
            if path_res.returncode == 0 and path_res.stdout.strip():
                filename = path_res.stdout.strip()

        except Exception as e:
            return jsonify({"status": "error", "message": f"SCP error: {str(e)}"}), 500

    return jsonify({"status": "success", "filename": filename})


@api_bp.route("/api/download/<path:filename>", methods=["GET"])
@authenticated_only
def download_file(filename):
    workspace_dir = os.path.join(env_config.DATA_DIR, "workspace")
    try:
        base_path = os.path.abspath(workspace_dir)
        target_path = os.path.abspath(os.path.join(base_path, filename))

        if not target_path.startswith(base_path):
            return jsonify({"status": "error", "message": "Access denied"}), 403

        if not os.path.isfile(target_path):
            return jsonify(
                {"status": "error", "message": f"File not found: {target_path}"}
            ), 404

        dir_name = os.path.dirname(target_path)
        base_name = os.path.basename(target_path)

        print(f"DEBUG: sending {base_name} from {dir_name}")
        return send_from_directory(dir_name, base_name, as_attachment=True)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route("/api/health")
def health_check():
    return jsonify({"status": "ok"})


@api_bp.route("/api/prompts", methods=["GET"])
@authenticated_only
def list_prompts():
    return jsonify(prompt_manager.list_prompts())


@api_bp.route("/api/prompts", methods=["POST"])
@authenticated_only
def save_prompt():
    data = request.json
    prompt_id = data.get("id")
    name = data.get("name")
    text = data.get("text")

    if not name or not text:
        return jsonify({"error": "Missing name or text"}), 400

    if prompt_id:
        success = prompt_manager.update_prompt(prompt_id, name, text)
        return jsonify({"status": "success" if success else "error"})
    else:
        new_id = prompt_manager.add_prompt(name, text)
        return jsonify({"status": "success", "id": new_id})


@api_bp.route("/api/prompts/<prompt_id>", methods=["DELETE"])
@authenticated_only
def delete_prompt(prompt_id):
    success = prompt_manager.delete_prompt(prompt_id)
    return jsonify({"status": "success" if success else "error"})
