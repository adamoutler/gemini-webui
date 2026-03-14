import os
import json
import shutil
import subprocess
import time
import socket
import datetime
import logging
from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

from src.app import get_config, get_config_paths, authenticated_only

logger = logging.getLogger(__name__)

host_key_bp = Blueprint("host_key", __name__)


@host_key_bp.route("/api/hosts", methods=["GET"])
@authenticated_only
def list_hosts():
    return jsonify(get_config().get("HOSTS", []))


@host_key_bp.route("/api/hosts", methods=["POST"])
@authenticated_only
def add_host():
    new_host = request.json
    label = new_host.get("label")
    old_label = new_host.get("old_label")
    if not label:
        return jsonify({"status": "error", "message": "Label is required"}), 400

    env_vars = new_host.get("env_vars")
    if env_vars is not None:
        if not isinstance(env_vars, dict):
            return jsonify(
                {"status": "error", "message": "env_vars must be a dictionary"}
            ), 400
        if len(env_vars) > 20:
            return jsonify(
                {"status": "error", "message": "Too many environment variables"}
            ), 400
        import re

        for k, v in env_vars.items():
            if not isinstance(k, str) or not isinstance(v, str):
                return jsonify(
                    {
                        "status": "error",
                        "message": "env_vars keys and values must be strings",
                    }
                ), 400
            if len(k) > 255 or len(v) > 1024:
                return jsonify(
                    {"status": "error", "message": "env_vars keys or values too long"}
                ), 400
            if not re.match(r"^[a-zA-Z0-9_]+$", k):
                return jsonify(
                    {
                        "status": "error",
                        "message": "env_vars keys must be alphanumeric and underscores",
                    }
                ), 400

    curr_conf = get_config()
    hosts = curr_conf.get("HOSTS", [])

    found_idx = -1
    search_label = old_label if old_label else label

    for i, h in enumerate(hosts):
        if h["label"] == search_label:
            found_idx = i
            break

    if found_idx != -1:
        hosts[found_idx] = {k: v for k, v in new_host.items() if k != "old_label"}
    else:
        hosts.append({k: v for k, v in new_host.items() if k != "old_label"})

    curr_conf["HOSTS"] = hosts
    _, config_file, _ = get_config_paths()
    with open(config_file, "w") as f:
        json.dump(curr_conf, f, indent=4)
    return jsonify({"status": "success"})


@host_key_bp.route("/api/hosts/reorder", methods=["POST"])
@authenticated_only
def reorder_hosts():
    new_order = request.json
    curr_conf = get_config()
    hosts = curr_conf.get("HOSTS", [])

    reordered = []
    host_map = {h["label"]: h for h in hosts}
    for label in new_order:
        if label in host_map:
            reordered.append(host_map[label])

    existing_labels = set(new_order)
    for h in hosts:
        if h["label"] not in existing_labels:
            reordered.append(h)

    curr_conf["HOSTS"] = reordered
    _, config_file, _ = get_config_paths()
    with open(config_file, "w") as f:
        json.dump(curr_conf, f, indent=4)
    return jsonify({"status": "success"})


@host_key_bp.route("/api/hosts/<label>", methods=["DELETE"])
@authenticated_only
def remove_host(label):
    if label == "local":
        return jsonify({"status": "error", "message": "Cannot delete local box"}), 403
    curr_conf = get_config()
    hosts = curr_conf.get("HOSTS", [])
    hosts = [h for h in hosts if h["label"] != label]
    curr_conf["HOSTS"] = hosts
    _, config_file, _ = get_config_paths()
    with open(config_file, "w") as f:
        json.dump(curr_conf, f, indent=4)
    return jsonify({"status": "success"})


@host_key_bp.route("/api/keys", methods=["GET"])
@authenticated_only
def list_ssh_keys():
    _, _, ssh_dir = get_config_paths()
    keys = []
    if os.path.exists(ssh_dir):
        for f in os.listdir(ssh_dir):
            if os.path.isfile(os.path.join(ssh_dir, f)) and f not in [
                "config",
                "known_hosts",
            ]:
                keys.append(f)
    return jsonify(keys)


@host_key_bp.route("/api/keys/public", methods=["GET"])
@authenticated_only
def get_public_key():
    _, _, ssh_dir = get_config_paths()
    pub_key_path = os.path.join(ssh_dir, "id_ed25519.pub")
    if os.path.exists(pub_key_path):
        with open(pub_key_path, "r") as f:
            return jsonify({"key": f.read().strip()})
    return jsonify({"error": "Public key not found"}), 404


@host_key_bp.route("/api/keys/rotate", methods=["POST"])
@authenticated_only
def rotate_instance_key():
    _, _, ssh_dir = get_config_paths()
    key_path = os.path.join(ssh_dir, "id_ed25519")
    try:
        if os.path.exists(key_path):
            timestamp = int(time.time())
            shutil.move(key_path, f"{key_path}.{timestamp}.bak")
            if os.path.exists(key_path + ".pub"):
                shutil.move(key_path + ".pub", f"{key_path}.{timestamp}.pub.bak")

        hostname = socket.gethostname()
        datestr = datetime.datetime.now().strftime("%Y%m%d")
        comment = f"gemini-webui-{hostname}-{datestr}"
        logger.info(f"Rotating instance SSH key with comment: {comment}...")
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", key_path, "-C", comment],
            check=True,
        )
        try:
            shutil.chown(key_path, user="node", group="node")
            shutil.chown(key_path + ".pub", user="node", group="node")
        except (LookupError, PermissionError):
            pass
        os.chmod(key_path, 0o600)

        with open(key_path + ".pub", "r") as f:
            return jsonify({"status": "success", "key": f.read().strip()})
    except Exception as e:
        logger.error(f"Failed to rotate SSH key: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@host_key_bp.route("/api/keys/text", methods=["POST"])
@authenticated_only
def add_ssh_key_text():
    if request.content_length and request.content_length > 10 * 1024:
        return jsonify({"status": "error", "message": "Payload too large"}), 400

    data = request.json
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

    raw_name = data.get("name")
    if not isinstance(raw_name, str):
        return jsonify({"status": "error", "message": "Invalid name format"}), 400

    name = secure_filename(raw_name)
    key_text = data.get("key")

    if not name or not key_text:
        return jsonify({"status": "error", "message": "Name and key are required"}), 400

    if not isinstance(key_text, str) or len(key_text) > 10 * 1024:
        return jsonify(
            {"status": "error", "message": "Invalid key format or size"}
        ), 400

    valid_prefixes = ("-----BEGIN ", "ssh-", "ecdsa-")
    if not any(key_text.lstrip().startswith(prefix) for prefix in valid_prefixes):
        return jsonify({"status": "error", "message": "Invalid SSH key format"}), 400

    if not key_text.endswith("\n"):
        key_text += "\n"
    _, _, ssh_dir = get_config_paths()
    save_path = os.path.join(ssh_dir, name)
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(key_text)
    os.chmod(save_path, 0o600)
    return jsonify({"status": "success", "filename": name})


@host_key_bp.route("/api/keys/upload", methods=["POST"])
@authenticated_only
def upload_ssh_key():
    if request.content_length and request.content_length > 10 * 1024:
        return jsonify({"status": "error", "message": "Payload too large"}), 400

    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "No selected file"}), 400

    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({"status": "error", "message": "Invalid filename"}), 400

    key_content = file.read(10 * 1024 + 1)
    if len(key_content) > 10 * 1024:
        return jsonify({"status": "error", "message": "File too large"}), 400

    try:
        key_text = key_content.decode("utf-8")
    except UnicodeDecodeError:
        return jsonify({"status": "error", "message": "Invalid file encoding"}), 400

    valid_prefixes = ("-----BEGIN ", "ssh-", "ecdsa-")
    if not any(key_text.lstrip().startswith(prefix) for prefix in valid_prefixes):
        return jsonify({"status": "error", "message": "Invalid SSH key format"}), 400

    _, _, ssh_dir = get_config_paths()
    save_path = os.path.join(ssh_dir, filename)
    with open(save_path, "wb") as f:
        f.write(key_content)
    os.chmod(save_path, 0o600)
    return jsonify({"status": "success", "filename": filename})


@host_key_bp.route("/api/keys/<filename>", methods=["DELETE"])
@authenticated_only
def remove_ssh_key(filename):
    filename = secure_filename(filename)
    _, _, ssh_dir = get_config_paths()
    path = os.path.join(ssh_dir, filename)
    if os.path.exists(path):
        os.remove(path)
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "File not found"}), 404
