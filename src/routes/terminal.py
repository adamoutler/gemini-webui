from src.shared_state import ephemeral_sessions
import os
import shlex
import subprocess
from flask import Blueprint, jsonify, request, session

from src.config import env_config
from src.session_manager import session_manager
from src.app import (
    get_config_paths,
    authenticated_only,
    logger,
    # removed direct import
    kill_and_reap,
    GEMINI_BIN,
    session_results_cache,
    session_results_cache_lock,
    socketio,
)
from src.utils import smart_file_search
from src.process_manager import (
    fetch_sessions_for_host,
    validate_ssh_target,
    get_remote_command_prefix,
)

terminal_bp = Blueprint("sessions", __name__)


@terminal_bp.route("/api/sessions/persisted", methods=["GET"])
@authenticated_only
def list_persisted_sessions():
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    if not session_manager.persistence:
        return jsonify({})
    all_persisted = session_manager.persistence.load()
    # Filter by user_id
    user_persisted = {
        tid: s for tid, s in all_persisted.items() if s.get("user_id") == user_id
    }
    return jsonify(user_persisted)


@terminal_bp.route("/api/migrate-tabs", methods=["POST"])
@authenticated_only
def migrate_tabs():
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    data = request.json
    tabs = data.get("tabs", [])
    if not tabs or not session_manager.persistence:
        return jsonify({"status": "ignored"})

    current_persisted = session_manager.persistence.load()
    updated = False
    for tab in tabs:
        tid = tab.get("tab_id")
        if tid and tid not in current_persisted:
            current_persisted[tid] = {
                "tab_id": tid,
                "title": tab.get("title"),
                "ssh_target": tab.get("ssh_target"),
                "ssh_dir": tab.get("ssh_dir"),
                "user_id": user_id,
                "resume": tab.get("resume", True),
            }
            updated = True

    if updated:
        session_manager.persistence.save(current_persisted)
        # Broadcast sync to other clients
        socketio.emit("sync-tabs", current_persisted, room=f"user_{user_id}")

    return jsonify({"status": "success"})


@terminal_bp.route("/api/management/sessions", methods=["GET"])
@authenticated_only
def list_active_sessions():
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    return jsonify(session_manager.list_sessions(user_id))


@terminal_bp.route("/api/management/sessions/<tab_id>", methods=["DELETE"])
@authenticated_only
def terminate_managed_session(tab_id):
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    if not tab_id:
        return jsonify({"error": "Tab ID required"}), 400

    # Remove from persistence first to prevent re-sync
    if session_manager.persistence:
        session_manager.persistence.remove(tab_id)

    session_obj = session_manager.remove_session(tab_id, user_id)
    if not session_obj:
        return jsonify({"error": "Session not found"}), 404

    logger.info(f"Terminating managed session {tab_id}")
    ephemeral_sessions.pop(tab_id, None)
    kill_and_reap(session_obj.pid)
    if session_obj.fd is not None:
        try:
            os.close(session_obj.fd)
        except OSError:
            pass

    # Broadcast termination to all clients in the room
    socketio.emit("session-terminated", {"tab_id": tab_id}, room=tab_id)
    return jsonify({"status": "success"})


@terminal_bp.route("/api/sessions/terminate_all", methods=["GET", "POST"])
@authenticated_only
def terminate_all_managed_sessions():
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    count = 0
    sessions_to_remove = session_manager.list_sessions(user_id)
    for s in sessions_to_remove:
        tab_id = s.get("tab_id")
        if not tab_id:
            continue

        # Remove from persistence
        if session_manager.persistence:
            session_manager.persistence.remove(tab_id)

        session_obj = session_manager.remove_session(tab_id, user_id)
        if session_obj:
            logger.info(f"Terminating managed session {tab_id}")
            ephemeral_sessions.pop(tab_id, None)
            if session_obj.pid is not None:
                kill_and_reap(session_obj.pid)
            if session_obj.fd is not None:
                try:
                    os.close(session_obj.fd)
                except OSError:
                    pass
            count += 1

        # Broadcast termination
        socketio.emit("session-terminated", {"tab_id": tab_id}, room=tab_id)

    return jsonify({"status": "success", "count": count})


@terminal_bp.route("/api/sessions/<session_id>/search_files", methods=["GET"])
@authenticated_only
def search_files(session_id):
    q = request.args.get("q", "")
    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    session_obj = session_manager.get_session(session_id, user_id)
    if not session_obj:
        logger.warning(
            f"search_files: Session {session_id} not found for user {user_id}. Available sessions: {list(session_manager.sessions.keys())}"
        )
        return jsonify({"error": "Session not found"}), 404
    matches = smart_file_search(session_obj.file_cache, q)
    return jsonify({"matches": matches})


def _get_gemini_sessions_impl(ssh_target, ssh_dir, cache_key, use_cache, bg):
    if use_cache:
        with session_results_cache_lock:
            if cache_key in session_results_cache:
                return session_results_cache[cache_key]

    if bg:
        with session_results_cache_lock:
            if not hasattr(_get_gemini_sessions_impl, "fetching_locks"):
                _get_gemini_sessions_impl.fetching_locks = set()
            should_fetch = cache_key not in _get_gemini_sessions_impl.fetching_locks
            if should_fetch:
                _get_gemini_sessions_impl.fetching_locks.add(cache_key)

        if should_fetch:

            def background_fetch(target, directory, key):
                try:
                    _, _, ssh_dir_path = get_config_paths()
                    res = fetch_sessions_for_host(
                        {
                            "target": target,
                            "dir": directory,
                            "type": "ssh" if target else "local",
                        },
                        ssh_dir_path,
                        GEMINI_BIN,
                    )
                    with session_results_cache_lock:
                        session_results_cache[key] = res
                except Exception as e:
                    logger.error(f"Background fetch error: {e}")
                    with session_results_cache_lock:
                        session_results_cache[key] = {"error": str(e)}
                finally:
                    with session_results_cache_lock:
                        if key in _get_gemini_sessions_impl.fetching_locks:
                            _get_gemini_sessions_impl.fetching_locks.remove(key)

            socketio.start_background_task(
                background_fetch, ssh_target, ssh_dir, cache_key
            )
        return {"status": "fetching"}

    _, _, ssh_dir_path = get_config_paths()
    result = fetch_sessions_for_host(
        {
            "target": ssh_target,
            "dir": ssh_dir,
            "type": "ssh" if ssh_target else "local",
        },
        ssh_dir_path,
        GEMINI_BIN,
    )
    with session_results_cache_lock:
        session_results_cache[cache_key] = result
    return result


@terminal_bp.route("/api/sessions", methods=["GET"])
@authenticated_only
def list_gemini_sessions():
    ssh_target = request.args.get("ssh_target")
    from src.process_manager import validate_ssh_target

    if ssh_target and not validate_ssh_target(ssh_target):
        return jsonify({"error": "Invalid target"}), 400
    ssh_dir = request.args.get("ssh_dir")
    cache_key = (
        f"{'ssh' if ssh_target else 'local'}:{ssh_target or 'local'}:{ssh_dir or ''}"
    )
    use_cache = request.args.get("cache") == "true"
    bg = request.args.get("bg") == "true"

    res = _get_gemini_sessions_impl(ssh_target, ssh_dir, cache_key, use_cache, bg)
    if (
        isinstance(res, dict)
        and isinstance(res.get("error"), str)
        and "timeout" in res["error"].lower()
    ):
        return jsonify(res), 504
    return jsonify(res)


@terminal_bp.route("/api/sessions/terminate", methods=["GET"])
@authenticated_only
def terminate_remote_session():
    data = request.json
    ssh_target = data.get("ssh_target")
    ssh_dir = data.get("ssh_dir")
    session_id = data.get("session_id")

    from src.process_manager import validate_ssh_target

    if ssh_target and not validate_ssh_target(ssh_target):
        return jsonify({"error": "Invalid target"}), 400

    if not session_id:
        return jsonify({"error": "Session ID required"}), 400

    import re

    # Validate session_id format to prevent command injection alerts
    if not re.match(r"^[a-zA-Z0-9_-]+$", str(session_id)):
        return jsonify({"error": "Invalid Session ID format"}), 400
    safe_session_id = str(session_id)

    if ssh_target:
        if not validate_ssh_target(ssh_target):
            return jsonify({"error": "Invalid SSH target"}), 400

        remote_prefix = get_remote_command_prefix(ssh_dir, GEMINI_BIN)
        remote_cmd = f"{remote_prefix} if command -v {GEMINI_BIN} >/dev/null 2>&1; then {GEMINI_BIN} --terminate {safe_session_id}; fi"
        login_wrapped_cmd = f"bash -ilc {shlex.quote(remote_cmd)}"

        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no"]
        _, _, ssh_dir_path = get_config_paths()
        known_hosts_path = os.path.join(ssh_dir_path, "known_hosts")
        cmd.extend(["-o", f"UserKnownHostsFile={known_hosts_path}"])
        if os.path.exists(ssh_dir_path):
            for f in os.listdir(ssh_dir_path):
                if (
                    os.path.isfile(os.path.join(ssh_dir_path, f))
                    and f not in ["config", "known_hosts"]
                    and not f.endswith(".pub")
                ):
                    cmd.extend(["-i", os.path.join(ssh_dir_path, f)])
        cmd.extend(["--", ssh_target, login_wrapped_cmd])
    else:
        cmd = [GEMINI_BIN, "--terminate", str(session_id)]

    try:
        subprocess.run(cmd, timeout=15, start_new_session=True)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": "An internal error occurred"}), 500


@terminal_bp.route("/api/test_inject_session", methods=["GET"])
def inject_sess():
    import time
    from src.session_manager import Session, session_manager

    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    s = Session("tab_backendtest123", 999, 9999, user_id=user_id)
    session_manager.add_session(s)
    return jsonify({"status": "injected"})
