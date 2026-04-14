import eventlet

eventlet.monkey_patch()
import eventlet.green.subprocess as subprocess
import os, time, weakref

_active_popens = weakref.WeakValueDictionary()
_known_pids = {}

orig_init = subprocess.Popen.__init__


def patched_init(self, *args, **kwargs):
    orig_init(self, *args, **kwargs)
    if getattr(self, "pid", None) is not None:
        _active_popens[id(self)] = self
        _known_pids[id(self)] = self.pid


subprocess.Popen.__init__ = patched_init


def run_abandoned():
    p = subprocess.Popen(["sleep", "0.5"])
    print("Spawned abandoned child", p.pid)
    # Don't wait, just exit. Local 'p' is GC'd.


run_abandoned()

time.sleep(1)  # Let it die and become zombie

# Check known pids
for obj_id, pid in list(_known_pids.items()):
    if obj_id not in _active_popens:
        print(f"Reaping abandoned PID {pid}")
        try:
            os.waitpid(pid, os.WNOHANG)
            print(f"Reaped {pid}")
        except Exception as e:
            print("Error", e)
