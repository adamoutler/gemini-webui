import re

with open("src/app.py", "r") as f:
    content = f.read()

# Add from src.extensions import socketio at the top of the file
if "from src.extensions import socketio" not in content:
    content = content.replace(
        "from flask_socketio import SocketIO,",
        "from flask_socketio import SocketIO,\nfrom src.extensions import socketio\n",
    )

# Replace socketio = SocketIO(...) with socketio.init_app(...)
content = re.sub(
    r'socketio = SocketIO\(app, cors_allowed_origins="\*", async_mode="eventlet"\)',
    'socketio.init_app(app, cors_allowed_origins="*", async_mode="eventlet")',
    content,
)

content = re.sub(
    r'socketio = SocketIO\(\s*app, cors_allowed_origins=allowed_origins, async_mode="eventlet"\s*\)',
    'socketio.init_app(app, cors_allowed_origins=allowed_origins, async_mode="eventlet")',
    content,
)

# Wrap socketio.init_app in if not getattr(socketio, 'server', None):
old_init = """if env_config.BYPASS_AUTH_FOR_TESTING:
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

new_init = """if not getattr(socketio, 'server', None):
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

content = content.replace(old_init, new_init)

with open("src/app.py", "w") as f:
    f.write(content)
