import time
import collections
import codecs

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
        self.decoder = codecs.getincrementaldecoder('utf-8')()
        self.buffer = collections.deque(maxlen=1000) # Store last 1000 chunks (up to ~20MB)
        self.last_seen = time.time()
        self.orphaned_at = None

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

    def add_session(self, session):
        self.sessions[session.tab_id] = session

    def get_session(self, tab_id, user_id=None):
        session = self.sessions.get(tab_id)
        if session and (user_id is None or session.user_id == user_id):
            return session
        return None

    def remove_session(self, tab_id, user_id=None):
        session = self.get_session(tab_id, user_id)
        if session:
            self.sessions.pop(tab_id, None)
            sid = self.tabid_to_sid.pop(tab_id, None)
            if sid: self.sid_to_tabid.pop(sid, None)
        return session

    def orphan_session(self, tab_id):
        session = self.get_session(tab_id)
        if session:
            session.orphaned_at = time.time()
            self.tabid_to_sid.pop(tab_id, None)

    def reclaim_session(self, tab_id, sid, user_id, on_steal=None):
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
        return [s.to_dict() for s in self.sessions.values() if s.user_id == user_id]
