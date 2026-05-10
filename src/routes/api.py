import os
import tempfile
import uuid
import shutil
import json
import zipfile
import logging
import secrets
import hashlib
import datetime
from flask import (
    Blueprint,
    jsonify,
    request,
    send_file,
    send_from_directory,
    session,
    after_this_request,
)
from werkzeug.utils import secure_filename
from flask_wtf.csrf import generate_csrf
from src.services.session_store import session_manager
from src.prompt_manager import prompt_manager
from src.config import env_config
from src.config import get_config, get_config_paths
from src.routes.auth_utils import authenticated_only
from marshmallow import Schema, fields
from src.decorators.validation import validate_json_schema

INTERNAL_ERR_MSG = "An internal error occurred"


class PromptSchema(Schema):
    id = fields.String(required=False)
    name = fields.String(required=True)
    text = fields.String(required=True)


class TaskKillSchema(Schema):
    tab_id = fields.String(required=True)


logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)


@api_bp.route("/api/config", methods=["GET"])
@authenticated_only
def get_current_config():
    conf = get_config()
    conf.pop("LDAP_BIND_SECRET", None)
    conf.pop("ADMIN_SECRET", None)
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
        return jsonify({"error": INTERNAL_ERR_MSG}), 500


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
        return jsonify({"error": INTERNAL_ERR_MSG}), 500


@api_bp.route("/api/csrf-token", methods=["GET"])
def get_csrf_token_endpoint():
    from flask import g

    # Clear the old token to force generation of a fresh, unexpired token
    if "csrf_token" in session:
        session.pop("csrf_token", None)
    if hasattr(g, "csrf_token"):
        delattr(g, "csrf_token")

    token = generate_csrf()
    response = jsonify({"csrf_token": token})
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@api_bp.route("/api/csrf", methods=["GET"])
def get_csrf_token():
    from flask import g

    if "csrf_token" in session:
        session.pop("csrf_token", None)
    if hasattr(g, "csrf_token"):
        delattr(g, "csrf_token")
    return jsonify({"csrf_token": generate_csrf()})


@api_bp.route("/api/upload", methods=["POST"])
@authenticated_only
def upload_file():
    try:
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
            ssh_dir = request.form.get("ssh_dir")
            from src.config import get_config_paths

            _, _, ssh_dir_path = get_config_paths()

            from src.services.remote_fs import upload_to_remote

            filename = upload_to_remote(
                save_path, filename, ssh_target, ssh_dir, ssh_dir_path
            )

        return jsonify({"status": "success", "filename": filename})
    except Exception:
        import traceback

        with open("/tmp/upload_err2.log", "w") as f:
            f.write(traceback.format_exc())
        return jsonify(
            {"status": "error", "message": "An internal error occurred during upload"}
        ), 500


@api_bp.route("/api/download/<path:filename>", methods=["GET"])
@authenticated_only
def download_file(filename):
    ssh_target = request.args.get("ssh_target")
    ssh_dir = request.args.get("ssh_dir")

    if ssh_target:
        from src.config import get_config_paths
        from src.services.remote_fs import download_from_remote

        _, _, ssh_dir_path = get_config_paths()
        try:
            local_path = download_from_remote(
                filename, ssh_target, ssh_dir, ssh_dir_path
            )

            @after_this_request
            def remove_file(response):
                try:
                    os.remove(local_path)
                except Exception:
                    pass
                return response

            return send_file(
                local_path, as_attachment=True, download_name=os.path.basename(filename)
            )
        except Exception as e:
            import traceback

            traceback.print_exc()
            return jsonify({"status": "error", "message": str(e)}), 500

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
    except Exception:
        import traceback

        traceback.print_exc()
        return jsonify({"status": "error", "message": INTERNAL_ERR_MSG}), 500


@api_bp.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"})


@api_bp.route("/api/prompts", methods=["GET"])
@authenticated_only
def list_prompts():
    return jsonify(prompt_manager.list_prompts())


@api_bp.route("/api/prompts", methods=["POST"])
@authenticated_only
@validate_json_schema(PromptSchema)
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


@api_bp.route("/api/tasks", methods=["GET"])
@authenticated_only
def list_tasks():
    res = {}
    with session_manager._lock:
        for tid, s in session_manager.sessions.items():
            uid = str(s.user_id) if s.user_id else "unknown"
            if uid not in res:
                res[uid] = []
            res[uid].append(
                {
                    "tab_id": s.tab_id,
                    "title": s.title,
                    "ssh_target": s.ssh_target,
                    "pid": s.pid,
                    "active": s.active,
                    "last_seen": s.last_seen,
                }
            )

    from src.shared_state import active_monitors, active_monitors_lock
    from flask import session

    uid = str(session.get("user_id")) if session.get("user_id") else "unknown"
    if env_config.BYPASS_AUTH_FOR_TESTING:
        uid = "admin"

    with active_monitors_lock:
        if active_monitors:
            if uid not in res:
                res[uid] = []
            for mid, m in active_monitors.items():
                res[uid].append(
                    {
                        "tab_id": f"monitor_{mid}",
                        "title": f"Connection Monitor ({m.get('target')})",
                        "ssh_target": m.get("target"),
                        "pid": m.get("pid"),
                        "active": True,
                        "last_seen": m.get("timestamp", 0),
                    }
                )

    return jsonify(res)


@api_bp.route("/api/tasks/kill", methods=["POST"])
@authenticated_only
@validate_json_schema(TaskKillSchema)
def kill_task():
    from flask import request
    import os
    import time

    data = request.json
    tab_id = data.get("tab_id")

    from src.infrastructure.process_manager import kill_and_reap

    if tab_id.startswith("monitor_"):
        mid = tab_id.replace("monitor_", "", 1)
        from src.shared_state import active_monitors, active_monitors_lock

        with active_monitors_lock:
            m = active_monitors.get(mid)
            if not m:
                return jsonify({"error": "Monitor not found"}), 404
            pid = m.get("pid")

        logger.info(
            f"[Task Monitor] Attempting to kill monitor task {mid} with PID {pid}"
        )
        kill_and_reap(pid)
        with active_monitors_lock:
            active_monitors.pop(mid, None)
        return jsonify({"status": "success"})

    with session_manager._lock:
        sess = session_manager.sessions.get(tab_id)
        if sess:
            from src.infrastructure.process_manager import kill_and_reap

            pid = sess.pid
            logger.info(
                f"[Task Monitor] Attempting to kill task {tab_id} with PID {pid}"
            )
            sess.active = False

            kill_and_reap(pid)

            # Verify if process is dead
            is_dead = False
            for _ in range(20):
                try:
                    # Check if already reaped or can be reaped
                    res = os.waitpid(pid, os.WNOHANG)
                    if res != (0, 0):
                        is_dead = True
                        break
                except ChildProcessError:
                    is_dead = True
                    break
                except OSError:
                    pass

                try:
                    os.kill(pid, 0)
                except OSError:
                    is_dead = True
                    break
                time.sleep(0.1)

            if not is_dead:
                logger.error(
                    f"[Task Monitor] PID {pid} is still alive (possible zombie) after kill attempt."
                )
                # We do not remove it if it's not confirmed dead, as per user requirement:
                # "each active connection should be added and removed only once confirmed dead"
                return jsonify(
                    {"error": f"Process {pid} failed to terminate. Possible zombie."}
                ), 500

            logger.info(f"[Task Monitor] PID {pid} confirmed dead. Removing session.")
            try:
                if sess.fd is not None:
                    os.close(sess.fd)
                    sess.fd = None
            except OSError:
                pass
            session_manager.remove_session(tab_id)
            session_manager.tabid_to_sids.pop(tab_id, None)
            if session_manager.persistence:
                session_manager.persistence.remove(tab_id)
            return jsonify({"status": "success"})
        return jsonify({"error": "Session not found"}), 404


def get_descendant_processes():
    """Reads /proc to find all children of the current process without needing psutil."""
    children = []
    import os

    my_pid = os.getpid()

    try:
        for pdir in os.listdir("/proc"):
            if not pdir.isdigit():
                continue
            try:
                stat_file = f"/proc/{pdir}/stat"
                if not os.path.exists(stat_file):
                    continue

                with open(stat_file, "r") as f:
                    stat_data = f.read().split()

                # stat_data[0] = pid, stat_data[1] = (comm), stat_data[2] = state, stat_data[3] = ppid
                ppid = int(stat_data[3])
                state = stat_data[2]

                # Check if it belongs to our application
                if ppid == my_pid:
                    with open(f"/proc/{pdir}/cmdline", "r") as cmd_f:
                        cmd = cmd_f.read().replace("\x00", " ").strip()

                    rss_pages = 0
                    with open(f"/proc/{pdir}/statm", "r") as m_f:
                        rss_pages = int(m_f.read().split()[1])

                    children.append(
                        {
                            "pid": int(pdir),
                            "state": state,
                            "command": cmd or stat_data[1].strip("()"),
                            "rss_memory_kb": rss_pages * 4,
                        }
                    )
            except (IOError, IndexError, ValueError):
                continue
    except OSError:
        pass

    return children


@api_bp.route("/api/processes", methods=["GET"])
@authenticated_only
def get_processes():
    return jsonify({"processes": get_descendant_processes()})


@api_bp.route("/api/processes/<int:target_pid>", methods=["DELETE"])
@authenticated_only
def kill_descendant_process(target_pid):
    import signal

    children = [p["pid"] for p in get_descendant_processes()]
    if target_pid not in children:
        return jsonify(
            {"error": "Permission denied. Process is not a child of this application."}
        ), 403

    try:
        os.killpg(target_pid, signal.SIGKILL)
    except OSError:
        try:
            os.kill(target_pid, signal.SIGKILL)
        except OSError as e:
            return jsonify({"error": str(e)}), 500

    return jsonify({"success": True, "pid": target_pid})
