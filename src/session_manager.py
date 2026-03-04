import os
import signal
import time
import collections
import codecs
import threading

class Session:
    def __init__(self, tab_id, fd, pid, user_id, title=None, ssh_target=None, ssh_dir=None, resume=True):
        self.tab_id = tab_id
        self.fd = fd
        self.pid = pid
        self.user_id = user_id
        self.title = title or ("Local" if not ssh_target else f"SSH: {ssh_target}")
        self.ssh_target = ssh_target
        self.ssh_dir = ssh_dir
        self.resume = resume
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.buffer = collections.deque() # Store chunks
        self.buffer_len = 0 # Track total string length
        self.max_buffer_len = 1024 * 256 # 256KB max scrollback
        self.last_seen = time.time()
        self.orphaned_at = None

    def append_buffer(self, text):
        self.buffer.append(text)
        self.buffer_len += len(text)
        while self.buffer_len > self.max_buffer_len and self.buffer:
            removed = self.buffer.popleft()
            self.buffer_len -= len(removed)

    def to_dict(self):
        return {
            "tab_id": self.tab_id,
            "title": self.title,
            "ssh_target": self.ssh_target,
            "ssh_dir": self.ssh_dir,
            "resume": self.resume,
            "last_active": self.last_seen,
            "is_orphaned": self.orphaned_at is not None
        }

class SessionManager:
    def __init__(self):
        self.sessions = {} # tab_id -> Session
        self.sid_to_tabid = {}
        self.tabid_to_sid = {}
        self._lock = threading.RLock()

    def add_session(self, session):
        with self._lock:
            user_sessions = [s for s in self.sessions.values() if s.user_id == session.user_id]
            if len(user_sessions) >= 10:
                user_sessions.sort(key=lambda s: s.last_seen)
                while len(user_sessions) >= 10:
                    oldest = user_sessions.pop(0)
                    try:
                        if oldest.fd is not None:
                            os.close(oldest.fd)
                    except OSError:
                        pass
                    try:
                        if oldest.pid is not None:
                            os.kill(oldest.pid, signal.SIGKILL)
                            os.waitpid(oldest.pid, os.WNOHANG)
                    except OSError:
                        pass
                    self.sessions.pop(oldest.tab_id, None)
                    sid = self.tabid_to_sid.pop(oldest.tab_id, None)
                    if sid:
                        self.sid_to_tabid.pop(sid, None)
            self.sessions[session.tab_id] = session

    def get_session(self, tab_id, user_id=None):
        with self._lock:
            session = self.sessions.get(tab_id)
            if session and (user_id is None or session.user_id == user_id):
                return session
            return None

    def get_all_sessions(self):
        with self._lock:
            return list(self.sessions.values())

    def remove_session(self, tab_id, user_id=None):
        with self._lock:
            session = self.get_session(tab_id, user_id)
            if session:
                self.sessions.pop(tab_id, None)
                sid = self.tabid_to_sid.pop(tab_id, None)
                if sid: self.sid_to_tabid.pop(sid, None)
            return session

    def orphan_session(self, tab_id):
        with self._lock:
            session = self.get_session(tab_id)
            if session:
                session.orphaned_at = time.time()
                self.tabid_to_sid.pop(tab_id, None)

    def reclaim_session(self, tab_id, sid, user_id, on_steal=None):
        with self._lock:
            session = self.get_session(tab_id, user_id)
            if session:
                # If already owned by another SID, disconnect that one
                old_sid = self.tabid_to_sid.get(tab_id)
                if old_sid and old_sid != sid:
                    # Decoupled notification
                    if on_steal:
                        on_steal(tab_id, old_sid)
                    self.sid_to_tabid.pop(old_sid, None)
                
                session.orphaned_at = None
                session.last_seen = time.time()
                self.sid_to_tabid[sid] = tab_id
                self.tabid_to_sid[tab_id] = sid
                return session
            return None

    def list_sessions(self, user_id):
        with self._lock:
            return [s.to_dict() for s in self.sessions.values() if s.user_id == user_id]
