import re

with open("src/app.py", "r") as f:
    content = f.read()

# Make sure register_socketio_handlers is called in init_app
# It needs to be imported first
idx = content.find("def init_app():")
import_stmt = "from src.gateways.terminal_socket import register_socketio_handlers\n"
content = content[:idx] + import_stmt + content[idx:]

with open("src/app.py", "w") as f:
    f.write(content)
