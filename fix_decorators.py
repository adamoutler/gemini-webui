import re

with open("src/app.py", "r") as f:
    content = f.read()

# Replace decorators
for event in [
    "connect",
    "disconnect",
    "join_room",
    "update_title",
    "pty-input",
    "pty-resize",
    "restart",
    "get_management_sessions",
    "get_sessions",
]:
    content = content.replace(f'@socketio.on("{event}")', "")

# Append registration block before register_blueprints
idx = content.find("def register_blueprints(app_instance):")
registration = """if not getattr(socketio, '_handlers_registered', False):
    socketio._handlers_registered = True
    socketio.on("connect")(handle_connect)
    socketio.on("disconnect")(handle_disconnect)
    socketio.on("join_room")(on_join_room)
    socketio.on("update_title")(update_title)
    socketio.on("pty-input")(pty_input)
    socketio.on("pty-resize")(pty_resize)
    socketio.on("restart")(pty_restart)
    socketio.on("get_management_sessions")(handle_get_management_sessions)
    socketio.on("get_sessions")(handle_get_sessions)

"""
content = content[:idx] + registration + content[idx:]

with open("src/app.py", "w") as f:
    f.write(content)
