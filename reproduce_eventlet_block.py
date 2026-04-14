import eventlet

eventlet.monkey_patch()
import subprocess
import time


def task_printing():
    while True:
        print("Still alive...")
        eventlet.sleep(1)


def task_blocking():
    print("Starting subprocess.run(timeout=5)...")
    # This should block for 5 seconds if it's not green
    try:
        subprocess.run(["sleep", "10"], timeout=5)
    except subprocess.TimeoutExpired:
        print("Subprocess timed out as expected")
    print("Subprocess finished")


eventlet.spawn(task_printing)
eventlet.spawn(task_blocking)

# Wait long enough to see if task_printing continues
eventlet.sleep(10)
