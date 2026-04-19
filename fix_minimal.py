import re

with open("src/app.py", "r") as f:
    content = f.read()

# 1. Add current_app
content = content.replace(
    "from flask import (", "from flask import (\n    current_app,"
)

# 2. Extract SocketIO instantiation
content = content.replace(
    "from flask_socketio import SocketIO, ConnectionRefusedError, join_room",
    "from flask_socketio import ConnectionRefusedError, join_room\nfrom src.extensions import socketio",
)

# Replace the socketio assignment
old_init_1 = 'socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")'
new_init_1 = 'socketio.init_app(app, cors_allowed_origins="*", async_mode="eventlet")'

old_init_2 = '    socketio = SocketIO(\n        app, cors_allowed_origins=allowed_origins, async_mode="eventlet"\n    )'
new_init_2 = '    socketio.init_app(\n        app, cors_allowed_origins=allowed_origins, async_mode="eventlet"\n    )'

content = content.replace(old_init_1, new_init_1).replace(old_init_2, new_init_2)

# Wrap it in if not getattr
old_block = """# Only allow origins from environment or localhost
if env_config.BYPASS_AUTH_FOR_TESTING:
    socketio.init_app(app, cors_allowed_origins="*", async_mode="eventlet")
else:
    # Default to '*' for ease of use if not specified, but log it
    allowed_origins_raw = env_config.ALLOWED_ORIGINS_RAW
    if allowed_origins_raw:
        allowed_origins = [
            o.strip() for o in allowed_origins_raw.split(",") if o.strip()
        ]
    else:
        logger.warning(
            "ALLOWED_ORIGINS not set. Defaulting to '*' (CORS restricted disabled)."
        )
        allowed_origins = "*"
    socketio.init_app(
        app, cors_allowed_origins=allowed_origins, async_mode="eventlet"
    )"""

new_block = """# Only allow origins from environment or localhost
if not getattr(socketio, 'server', None):
    if env_config.BYPASS_AUTH_FOR_TESTING:
        socketio.init_app(app, cors_allowed_origins="*", async_mode="eventlet")
    else:
        allowed_origins_raw = env_config.ALLOWED_ORIGINS_RAW
        if allowed_origins_raw:
            allowed_origins = [
                o.strip() for o in allowed_origins_raw.split(",") if o.strip()
            ]
        else:
            logger.warning(
                "ALLOWED_ORIGINS not set. Defaulting to '*' (CORS restricted disabled)."
            )
            allowed_origins = "*"
        socketio.init_app(
            app, cors_allowed_origins=allowed_origins, async_mode="eventlet"
        )"""

content = content.replace(old_block, new_block)

# 3. Replace app.config and app.logger in socket handlers
start_idx = content.find('@socketio.on("connect")')
end_idx = content.find("def register_blueprints(app_instance):")

if start_idx != -1 and end_idx != -1:
    handlers = content[start_idx:end_idx]
    handlers = handlers.replace("app.logger", "current_app.logger")
    handlers = handlers.replace("app.config", "current_app.config")
    content = content[:start_idx] + handlers + content[end_idx:]

with open("src/app.py", "w") as f:
    f.write(content)
