import re

with open("src/app.py", "r") as f:
    content = f.read()

# Find where handlers start
idx_start = content.find('@socketio.on("connect")')
idx_end = content.find("def register_blueprints(app_instance):")

handlers = content[idx_start:idx_end]

wrapped = "def register_socketio_handlers(app):\n"
for line in handlers.splitlines():
    if line:
        wrapped += "    " + line + "\n"
    else:
        wrapped += "\n"

content = content[:idx_start] + wrapped + content[idx_end:]
with open("src/app.py", "w") as f:
    f.write(content)
