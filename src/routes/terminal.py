from src.shared_state import (
    ephemeral_sessions,
    session_results_cache,
    session_results_cache_lock,
)
import os
import shlex
import subprocess
from flask import Blueprint, jsonify, request, session

from src.config import env_config, get_config_paths
from src.session_manager import session_manager
from src.routes.auth_utils import authenticated_only
import logging

logger = logging.getLogger(__name__)

from src.process_manager import (
    fetch_sessions_for_host,
    validate_ssh_target,
    get_remote_command_prefix,
    kill_and_reap,
)
from src.config import env_config
from src.extensions import socketio
from src.utils import smart_file_search

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
                        env_config.GEMINI_BIN,
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
        env_config.GEMINI_BIN,
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


@terminal_bp.route("/api/test_inject_session", methods=["GET"])
def inject_sess():
    import time
    from src.session_manager import session_manager
    from src.models.session import Session

    user_id = session.get("user_id") or (
        "admin" if env_config.BYPASS_AUTH_FOR_TESTING else None
    )
    s = Session("tab_backendtest123", 999, 9999, user_id=user_id)
    session_manager.add_session(s)
    return jsonify({"status": "injected"})
