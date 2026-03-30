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
    session_obj = session_manager.remove_session(tab_id, user_id)
    if session_obj:
        logger.info(f"Terminating managed session {tab_id}")
        ephemeral_sessions.pop(tab_id, None)
        kill_and_reap(session_obj.pid)
        if session_obj.fd is not None:
            try:
                os.close(session_obj.fd)
            except OSError:
                pass
        return jsonify({"status": "success"})
    return jsonify({"error": "Session not found"}), 404


@terminal_bp.route("/api/sessions/terminate_all", methods=["POST"])
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


@terminal_bp.route("/api/sessions/terminate", methods=["POST"])
@authenticated_only
def terminate_remote_session():
    data = request.json
    ssh_target = data.get("ssh_target")
    ssh_dir = data.get("ssh_dir")
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"error": "Session ID required"}), 400

    if ssh_target:
        if not validate_ssh_target(ssh_target):
            return jsonify({"error": "Invalid SSH target"}), 400

        remote_prefix = get_remote_command_prefix(ssh_dir, GEMINI_BIN)
        remote_cmd = f"{remote_prefix} if command -v {GEMINI_BIN} >/dev/null 2>&1; then {GEMINI_BIN} --terminate {shlex.quote(str(session_id))}; fi"
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
        subprocess.run(cmd)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
