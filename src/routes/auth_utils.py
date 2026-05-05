import logging
from functools import wraps
from flask import session
from src.config import env_config

logger = logging.getLogger(__name__)


def authenticated_only(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not env_config.BYPASS_AUTH_FOR_TESTING:
            if not session.get("authenticated"):
                return {"error": "unauthenticated"}, 401
        return f(*args, **kwargs)

    return wrapped
