import sys, re

with open("src/app.py", "r") as f:
    content = f.read()

# 1. Update imports
content = content.replace("from flask import (", "from flask import current_app, (")

# 2. Fix socketio.init_app
old_init = """if env_config.BYPASS_AUTH_FOR_TESTING:
    socketio.init_app(app, cors_allowed_origins="*", async_mode="eventlet")
else:
    # Default to '*' for ease of use if not specified, but log it
    allowed_origins_raw = env_config.ALLOWED_ORIGINS_RAW
    if allowed_origins_raw:
        allowed_origins = allowed_origins_raw.split(",")
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
        allowed_origins_raw = env_config.ALLOWED_ORIGINS_RAW
        if allowed_origins_raw:
            allowed_origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]
        else:
            logger.warning(
                "ALLOWED_ORIGINS not set. Defaulting to '*' (CORS restricted disabled)."
            )
            allowed_origins = "*"
        socketio.init_app(
            app, cors_allowed_origins=allowed_origins, async_mode="eventlet"
        )"""
content = content.replace(old_init, new_init)

# 3. Replace app.logger / app.config inside handlers
# We only want to replace them inside the handlers.
# Handlers are between @socketio.on("connect") and def register_blueprints
start_idx = content.find('@socketio.on("connect")')
end_idx = content.find("def register_blueprints(app_instance):")

if start_idx != -1 and end_idx != -1:
    handlers = content[start_idx:end_idx]
    handlers = handlers.replace("app.logger", "current_app.logger")
    handlers = handlers.replace("app.config", "current_app.config")

    # Wrap in register_socketio_handlers(app)
    lines = handlers.splitlines()
    wrapped_lines = ["def register_socketio_handlers(app):"]
    for line in lines:
        if line == "":
            wrapped_lines.append("")
        else:
            wrapped_lines.append("    " + line)

    content = (
        content[:start_idx] + "\n".join(wrapped_lines) + "\n\n" + content[end_idx:]
    )

with open("src/app.py", "w") as f:
    f.write(content)
