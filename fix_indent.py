import sys

with open("src/app.py", "r") as f:
    lines = f.readlines()

out = []
for line in lines:
    if line.startswith('if not getattr(socketio, "_handlers_registered"'):
        continue
    if line.startswith("    socketio._handlers_registered = True"):
        continue
    if line.startswith("def register_socketio_handlers(app):"):
        # Remove duplicate
        if out and out[-1].startswith("def register_socketio_handlers(app):"):
            continue
        out.append(line)
        continue

    if line.startswith('    @socketio.on("connect")'):
        # Fix indentation
        pass

    out.append(line)

with open("src/app.py", "w") as f:
    f.writelines(out)
