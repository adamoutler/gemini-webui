import time
from src.app import app, socketio


def bg_task():
    try:
        print("Emitting...", flush=True)
        socketio.emit("test", {"data": 123})
        print("Success!", flush=True)
    except Exception as e:
        print(f"Error: {e}", flush=True)


with app.app_context():
    socketio.start_background_task(bg_task)
    time.sleep(1)
