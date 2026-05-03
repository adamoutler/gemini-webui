from functools import wraps
from flask import request, Response, session, current_app
import hashlib
from src.config import get_config

from src.auth_ldap import check_auth
from src.config import env_config


def authenticate():
    return Response(
        "Login Required", 401, {"WWW-Authenticate": 'Basic realm="Login Required"'}
    )


def authenticated_only(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        bypass = env_config.BYPASS_AUTH_FOR_TESTING
        is_auth = session.get("authenticated")
        if bypass or is_auth:
            return f(*args, **kwargs)
        return authenticate()

    return wrapped


def require_auth():
    if (
        env_config.BYPASS_AUTH_FOR_TESTING
        or current_app.config.get("BYPASS_AUTH_FOR_TESTING") == "true"
    ):
        session["authenticated"] = True
        return

    if (
        request.path
        in [
            "/health",
            "/api/health",
            "/favicon.ico",
            "/favicon.svg",
            "/manifest.json",
            "/sw.js",
        ]
        or request.path.startswith("/s/")
        or request.path.startswith("/api/v1/")
    ):
        return

    auth = request.authorization

    LDAP_SERVER = current_app.config.get("LDAP_SERVER")
    LDAP_BASE_DN = current_app.config.get("LDAP_BASE_DN")
    LDAP_BIND_USER_DN = current_app.config.get("LDAP_BIND_USER_DN")
    LDAP_BIND_PASS = current_app.config.get("LDAP_BIND_PASS")
    LDAP_AUTHORIZED_GROUP = current_app.config.get("LDAP_AUTHORIZED_GROUP")
    LDAP_FALLBACK_DOMAIN = current_app.config.get("LDAP_FALLBACK_DOMAIN")
    ADMIN_USER = current_app.config.get("ADMIN_USER")
    ADMIN_PASS = current_app.config.get("ADMIN_PASS")

    # EXCLUSIVE AUTHENTICATION:
    # If LDAP is configured, it is the ONLY allowed method.
    if LDAP_SERVER:
        if auth and check_auth(
            auth.username,
            auth.password,
            LDAP_SERVER,
            LDAP_BASE_DN,
            LDAP_BIND_USER_DN,
            LDAP_BIND_PASS,
            LDAP_AUTHORIZED_GROUP,
            LDAP_FALLBACK_DOMAIN,
        ):
            session["authenticated"] = True
            session["user_id"] = auth.username
            return
    else:
        # Fall back to local admin credentials ONLY if LDAP is not configured.
        if auth and auth.username == ADMIN_USER and auth.password == ADMIN_PASS:
            session["authenticated"] = True
            session["user_id"] = ADMIN_USER
            return

    if not session.get("authenticated"):
        return authenticate()


def bearer_token_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return {"error": "Unauthorized"}, 401
        token = auth_header[7:]
        hashed_token = hashlib.sha256(token.encode()).hexdigest()
        conf = get_config()
        if hashed_token not in conf.get("API_KEYS", []):
            return {"error": "Unauthorized"}, 401
        return f(*args, **kwargs)

    return wrapped


def api_key_required(f):
    return bearer_token_required(f)
