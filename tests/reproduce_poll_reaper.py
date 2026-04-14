import eventlet

eventlet.monkey_patch()
import eventlet.green.subprocess as subprocess
import os, time

_spawned_popens = set()
orig_init = subprocess.Popen.__init__


def patched_init(self, *args, **kwargs):
    orig_init(self, *args, **kwargs)
    if hasattr(self, "pid") and self.pid is not None:
        _spawned_popens.add(self)


subprocess.Popen.__init__ = patched_init


def run_abandoned():
    try:
        subprocess.run(["sleep", "0.5"])
    except eventlet.greenlet.GreenletExit:
        pass


g = eventlet.spawn(run_abandoned)
eventlet.sleep(0.1)
g.kill()
eventlet.sleep(1)

print("Spawned popens size:", len(_spawned_popens))
for p in list(_spawned_popens):
    if p.poll() is not None:
        _spawned_popens.remove(p)

print("Spawned popens size after poll:", len(_spawned_popens))
os.system("ps -ef | grep sleep | grep -v grep")
