with open("src/app.py", "r") as f:
    content = f.read()

old_init = """# Only allow origins from environment or localhost
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

new_init = """# Only allow origins from environment or localhost
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

content = content.replace(old_init, new_init)
with open("src/app.py", "w") as f:
    f.write(content)
