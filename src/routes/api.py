import os
import subprocess
import tempfile
import uuid
import shutil
import json
import zipfile
import shlex
import logging
from flask import Blueprint, jsonify, request, send_file, send_from_directory
from werkzeug.utils import secure_filename
from flask_wtf.csrf import generate_csrf

from src.config import env_config
from src.app import get_config, get_config_paths, authenticated_only, logger
from src.process_manager import validate_ssh_target, build_ssh_args

api_bp = Blueprint("api", __name__)


@api_bp.route("/api/config", methods=["GET"])
@authenticated_only
def get_current_config():
    conf = get_config()
    conf.pop("LDAP_BIND_PASS", None)
    conf.pop("ADMIN_PASS", None)
    return jsonify(conf)


@api_bp.route("/api/config", methods=["POST"])
@authenticated_only
def update_config():
    new_conf = request.json
    curr_conf = get_config()
    curr_conf.update(new_conf)
    _, config_file, _ = get_config_paths()
    with open(config_file, "w") as f:
        json.dump(curr_conf, f, indent=4)
    return jsonify({"status": "success"})


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

        # Extract the uploaded zip file, preserving crucial Unix permissions.
        # Python's default ZipFile.extractall() drops file permissions. 
        # For SSH keys (.ssh/id_ed25519) to work securely, they require 
        # strictly restrictive permissions (0o600). We parse the raw zip header
        # external attributes to reconstruct the original Unix permissions.
        with zipfile.ZipFile(temp_zip, "r") as zip_ref:
            for info in zip_ref.infolist():
                extracted_path = zip_ref.extract(info, data_dir)
                if info.external_attr > 0:
                    # Unix attributes are stored in the high 16 bits
                    perms = info.external_attr >> 16
                    if perms != 0:
                        os.chmod(extracted_path, perms)

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
