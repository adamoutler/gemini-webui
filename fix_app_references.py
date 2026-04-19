import re

with open("src/app.py", "r") as f:
    content = f.read()

# Add current_app import
content = content.replace("from flask import (", "from flask import current_app, (")

# Only replace inside handlers
# The handlers are now just def handle_connect, def handle_disconnect, etc.
# We will use regex to find the bodies of these functions and replace app. with current_app.
for func in [
    "handle_connect",
    "handle_disconnect",
    "on_join_room",
    "update_title",
    "pty_input",
    "pty_resize",
    "pty_restart",
    "handle_get_management_sessions",
    "handle_get_sessions",
]:
    # Replace app.config and app.logger in the function body
    content = re.sub(
        f"(def {func}\(.*?):(.*?)(\n\n\n|\Z)",
        lambda m: m.group(1)
        + ":"
        + m.group(2)
        .replace("app.logger", "current_app.logger")
        .replace("app.config", "current_app.config"),
        content,
        flags=re.DOTALL,
    )

with open("src/app.py", "w") as f:
    f.write(content)
