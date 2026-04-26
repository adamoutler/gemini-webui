import os
import subprocess
import shlex

try:
    from config import env_config
    from services.process_engine import build_ssh_args, get_remote_command_prefix
except ImportError:
    from src.config import env_config
    from src.services.process_engine import build_ssh_args, get_remote_command_prefix
import signal
import time
import collections
import codecs
import threading
import fcntl
import os
import eventlet.greenio


try:
    from models.session import Session
except ImportError:
    from src.models.session import Session

import json


class SessionPersistenceManager:
    def __init__(self, data_dir):
        self.file_path = os.path.join(data_dir, "persisted_sessions.json")
        self._lock = threading.Lock()

    def load(self):
        with self._lock:
            if os.path.exists(self.file_path):
                try:
                    with open(self.file_path, "r") as f:
                        return json.load(f)
                except Exception:
                    return {}
            return {}

    def save(self, sessions_dict):
        with self._lock:
            try:
                # Filter out sensitive or ephemeral data
                data_to_save = {}
                for tid, s in sessions_dict.items():
                    data_to_save[tid] = {
                        "tab_id": s.get("tab_id"),
                        "title": s.get("title"),
                        "ssh_target": s.get("ssh_target"),
                        "ssh_dir": s.get("ssh_dir"),
                        "user_id": s.get("user_id"),
                        "resume": s.get("resume"),
                    }
                with open(self.file_path, "w") as f:
                    json.dump(data_to_save, f)
            except Exception as e:
                print(f"Error saving persisted sessions: {e}")

    def add(self, session_obj):
        sessions = self.load()
        sessions[session_obj.tab_id] = {
            "tab_id": session_obj.tab_id,
            "title": session_obj.title,
            "ssh_target": session_obj.ssh_target,
            "ssh_dir": session_obj.ssh_dir,
            "user_id": session_obj.user_id,
            "resume": session_obj.resume,
        }
        self.save(sessions)

    def remove(self, tab_id):
        sessions = self.load()
        if tab_id in sessions:
            sessions.pop(tab_id)
            self.save(sessions)


class SessionManager:
    def __init__(self, data_dir=None):
        self.sessions = {}  # tab_id -> Session
        self.sid_to_tabid = {}  # sid -> tab_id
        self.tabid_to_sids = {}  # tab_id -> set(sids)
        self._lock = threading.RLock()
        self.persistence = None
        if data_dir:
            self.persistence = SessionPersistenceManager(data_dir)

    def add_session(self, session, on_remove=None):
        with self._lock:
            # If a session with the same tab_id already exists, kill it first
            old_same_tab = self.sessions.pop(session.tab_id, None)
            if old_same_tab and old_same_tab is not session:
                old_same_tab.active = False
                if on_remove:
                    on_remove(old_same_tab.pid)
                else:
                    try:
                        if old_same_tab.pid is not None:
                            try:
                                if os.getpgid(old_same_tab.pid) != os.getpgrp():
                                    os.killpg(
                                        os.getpgid(old_same_tab.pid), signal.SIGKILL
                                    )
                                else:
                                    os.kill(old_same_tab.pid, signal.SIGKILL)
                            except OSError:
                                pass
                    except OSError:
                        try:
                            if old_same_tab.pid is not None:
                                os.kill(old_same_tab.pid, signal.SIGKILL)
                        except OSError:
                            pass
                try:
                    if old_same_tab.fd is not None:
                        os.close(old_same_tab.fd)
                except OSError:
                    pass

            user_sessions = [
                s for s in self.sessions.values() if s.user_id == session.user_id
            ]
            # Increased limit from 10 to 50 for auto-pinning support
            if len(user_sessions) >= 50:
                # Eviction policy: Only evict sessions with 0 active clients (SIDs)
                idle_sessions = [
                    s
                    for s in user_sessions
                    if len(self.tabid_to_sids.get(s.tab_id, set())) == 0
                ]
                idle_sessions.sort(key=lambda s: s.last_seen)

                if idle_sessions:
                    oldest = idle_sessions.pop(0)
                    oldest.active = False
                    if on_remove:
                        on_remove(oldest.pid)
                    else:
                        try:
                            if oldest.pid is not None:
                                try:
                                    if os.getpgid(oldest.pid) != os.getpgrp():
                                        os.killpg(
                                            os.getpgid(oldest.pid), signal.SIGKILL
                                        )
                                    else:
                                        os.kill(oldest.pid, signal.SIGKILL)
                                except OSError:
                                    pass
                        except OSError:
                            try:
                                if oldest.pid is not None:
                                    os.kill(oldest.pid, signal.SIGKILL)
                            except OSError:
                                pass
                    try:
                        if oldest.fd is not None:
                            os.close(oldest.fd)
                    except OSError:
                        pass
                    self.sessions.pop(oldest.tab_id, None)
                    self.tabid_to_sids.pop(oldest.tab_id, None)

            self.sessions[session.tab_id] = session
            if session.tab_id not in self.tabid_to_sids:
                self.tabid_to_sids[session.tab_id] = set()

            if self.persistence:
                self.persistence.add(session)

    def get_session(self, tab_id, user_id=None):
        with self._lock:
            session = self.sessions.get(tab_id)
            if session and (user_id is None or session.user_id == user_id):
                return session
            return None

    def get_all_sessions(self):
        with self._lock:
            return list(self.sessions.values())

    def update_title(self, tab_id, new_title, user_id=None, user_named=False):
        with self._lock:
            session = self.get_session(tab_id, user_id)
            if session:
                session.title = new_title
                if user_named:
                    session.user_named = True
                if self.persistence:
                    self.persistence.add(session)

    def remove_session(self, tab_id, user_id=None):
        import os

        with self._lock:
            session = self.get_session(tab_id, user_id)
            if session:
                session.active = False
                try:
                    if session.fd is not None:
                        os.close(session.fd)
                        session.fd = None
                except OSError:
                    pass
                self.sessions.pop(tab_id, None)
                sids = self.tabid_to_sids.pop(tab_id, set())
                for sid in sids:
                    self.sid_to_tabid.pop(sid, None)
                if self.persistence:
                    self.persistence.remove(tab_id)
            return session

    def orphan_session(self, tab_id, sid=None):
        with self._lock:
            session = self.get_session(tab_id)
            if session:
                if sid:
                    self.sid_to_tabid.pop(sid, None)
                    if tab_id in self.tabid_to_sids:
                        self.tabid_to_sids[tab_id].discard(sid)

                # Only mark as orphaned if NO clients are connected
                if len(self.tabid_to_sids.get(tab_id, set())) == 0:
                    session.orphaned_at = time.time()

    def reclaim_session(self, tab_id, sid, user_id):
        with self._lock:
            session = self.get_session(tab_id, user_id)
            if session:
                session.orphaned_at = None
                session.last_seen = time.time()
                self.sid_to_tabid[sid] = tab_id
                if tab_id not in self.tabid_to_sids:
                    self.tabid_to_sids[tab_id] = set()
                self.tabid_to_sids[tab_id].add(sid)
                return session
            return None

    def list_sessions(self, user_id):
        with self._lock:
            return [s.to_dict() for s in self.sessions.values() if s.user_id == user_id]

    def update_file_cache(self, tab_id, app_config):
        session = self.get_session(tab_id)
        if not session:
            return

        find_cmd = 'find . -maxdepth 5 \\( -type d -printf "%p/\\n" -o -type f -print \\) | grep -v "/\\." | grep -v "node_modules" | grep -v "__pycache__"'

        if session.ssh_target:
            ssh_dir_path = app_config.get("SSH_DIR", "~/.ssh")
            remote_prefix = get_remote_command_prefix(session.ssh_dir)
            remote_cmd = f"{remote_prefix} {find_cmd}"
            cmd = build_ssh_args(session.ssh_target, ssh_dir_path)
            cmd.extend(["--", session.ssh_target, f"bash -c {shlex.quote(remote_cmd)}"])
        else:
            data_dir = env_config.DATA_DIR
            work_dir = os.path.join(data_dir, "workspace")
            if os.path.exists(work_dir):
                cmd = ["/bin/sh", "-c", f"cd {shlex.quote(work_dir)} && {find_cmd}"]
            else:
                cmd = ["/bin/sh", "-c", find_cmd]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                session.file_cache = result.stdout.strip().split("\n")
        except Exception:
            pass


data_dir = env_config.DATA_DIR if "env_config" in globals() else None
session_manager = SessionManager(data_dir=data_dir)
