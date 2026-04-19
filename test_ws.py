import socketio
import time

sio = socketio.Client()
sio.connect("http://localhost:17566")
print("Connected!", sio.connected)
res = sio.call("get_sessions", {"bg": True, "cache": True})
print("get_sessions response:", res)
sio.disconnect()
