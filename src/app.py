import os
import sys
import eventlet
import eventlet.debug

if os.environ.get("SKIP_MONKEY_PATCH") != "true":
    eventlet.monkey_patch()
    eventlet.debug.hub_prevent_multiple_readers(False)

import logging
import json
from flask import Flask, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_wtf.csrf import CSRFError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import env_config, get_config, get_config_paths
from src.extensions import socketio, csrf, talisman
from src.auth import require_auth

if not env_config.SKIP_MONKEY_PATCH:
    try:
        from infrastructure.process_manager import apply_subprocess_monkey_patch
    except ImportError:
        from src.infrastructure.process_manager import apply_subprocess_monkey_patch
    apply_subprocess_monkey_patch()

logger = logging.getLogger(__name__)

# Re-export share_manager and IDENTIFICATION_REGEX for backward compatibility for now
from src.share_manager import ShareManager

share_manager = ShareManager()

from src.constants import IDENTIFICATION_REGEX

try:
    with open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION"
        ),
        "r",
    ) as f:
        APP_VERSION = f.read().strip()
except Exception as e:
    logger.warning(f"Failed to read VERSION: {e}")
    APP_VERSION = "unknown"


def create_app(test_config=None):
    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    app = Flask(__name__, template_folder=template_dir)

    app.wsgi_app = ProxyFix(
        app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
    )

    if test_config:
        app.config.update(test_config)

    data_dir, config_file, ssh_dir = get_config_paths()
    logger.info(f"Initializing app with DATA_DIR: {data_dir}")

    from src.bootstrap import setup_environment

    setup_environment(data_dir, ssh_dir)

    config = get_config()

    import secrets

    secret_key = config.get("SECRET_KEY") or env_config.SECRET_KEY
    if not secret_key:
        secret_key = secrets.token_hex(32)
        if config.get("DATA_WRITABLE"):
            try:
                config["SECRET_KEY"] = secret_key
                with open(config_file, "w") as f:
                    json.dump(config, f, indent=4)
            except Exception as e:
                pass

    app.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=False,
        SESSION_COOKIE_SAMESITE="Lax",
        DATA_DIR=data_dir,
        WTF_CSRF_ENABLED=not app.config.get("TESTING", False),
    )

    # Initialize extensions
    csrf.init_app(app)

    csp = {
        "default-src": "'self'",
        "script-src": [
            "'self'",
            "https://cdn.jsdelivr.net",
            "https://cdnjs.cloudflare.com",
            "https://unpkg.com",
        ],
        "style-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
        "connect-src": [
            "'self'",
            "ws:",
            "wss:",
            "http:",
            "https:",
            "https://cdn.jsdelivr.net",
            "https://cdnjs.cloudflare.com",
        ],
        "manifest-src": ["'self'"],
    }
    talisman.init_app(
        app,
        content_security_policy=csp,
        force_https=False,
        strict_transport_security=True,
        session_cookie_secure=False,
    )

    # Initialize socketio
    if getattr(socketio, "server", None) is None:
        if env_config.BYPASS_AUTH_FOR_TESTING:
            socketio.init_app(app, cors_allowed_origins="*", async_mode="eventlet")
        else:
            allowed_origins_raw = env_config.ALLOWED_ORIGINS_RAW
            if allowed_origins_raw:
                allowed_origins = allowed_origins_raw.split(",")
            else:
                allowed_origins = "*"
            socketio.init_app(
                app, cors_allowed_origins=allowed_origins, async_mode="eventlet"
            )

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        return jsonify(
            {"error": "CSRF token missing or incorrect", "csrf_expired": True}
        ), 400

    @app.context_processor
    def inject_version():
        return dict(version=APP_VERSION)

    app.before_request(require_auth)

    # Register blueprints
    from src.routes.host_keys import host_key_bp
    from src.routes.ui import ui_bp
    from src.routes.api import api_bp
    from src.routes.terminal import terminal_bp
    from src.routes.shares import shares_bp
    from src.routes.external_api import external_api_bp

    app.register_blueprint(host_key_bp)
    app.register_blueprint(ui_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(terminal_bp)
    app.register_blueprint(shares_bp)
    app.register_blueprint(external_api_bp)

    return app


# Provide a global app instance for backward compatibility with WSGI servers and tests
app = create_app()

if __name__ == "__main__":
    if not app.config.get("TESTING"):
        from src.infrastructure.process_manager import (
            cleanup_orphaned_ptys,
            zombie_reaper_task,
        )

        if (
            os.environ.get("WERKZEUG_RUN_MAIN") == "true"
            or not env_config.FLASK_USE_RELOADER
        ):
            from src.services.session_store import session_manager

            socketio.start_background_task(
                cleanup_orphaned_ptys, app, session_manager, env_config
            )
            socketio.start_background_task(zombie_reaper_task)

            from src.services.session_poller import session_poller_manager

            session_poller_manager.start()
            if not env_config.SKIP_PRELOADER:
                import src.gateways.terminal_socket

                socketio.start_background_task(
                    src.gateways.terminal_socket.background_session_preloader
                )

    debug_mode = env_config.FLASK_DEBUG
    use_reloader = env_config.FLASK_USE_RELOADER
    socketio.run(
        app,
        host="0.0.0.0",
        port=env_config.PORT,
        debug=debug_mode,
        use_reloader=use_reloader,
    )
