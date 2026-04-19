import codecs
import collections
import time
import fcntl
import os


class Session:
    def __init__(
        self,
        tab_id,
        fd,
        pid,
        user_id,
        title=None,
        ssh_target=None,
        ssh_dir=None,
        resume=True,
    ):
        self.tab_id = tab_id
        self.fd = fd
        self.pid = pid
        self.user_id = user_id
        self.title = title or ("Local" if not ssh_target else f"SSH: {ssh_target}")
        self.ssh_target = ssh_target
        self.ssh_dir = ssh_dir
        self.resume = resume
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.buffer = collections.deque()  # Store chunks
        self.buffer_len = 0  # Track total string length
        self.max_buffer_len = 1024 * 256  # 256KB max scrollback
        self.last_seen = time.time()
        self.orphaned_at = None
        self.file_cache = []
        self.active = True

        # Set the FD to non-blocking mode to prevent Eventlet hub lockups.
        # When O_NONBLOCK is set, Eventlet's monkey-patched os.read/os.write
        # will automatically yield to the hub (using trampoline) instead of blocking.
        if fd is not None:
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

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
            "is_orphaned": self.orphaned_at is not None,
            "file_cache": self.file_cache,
        }
