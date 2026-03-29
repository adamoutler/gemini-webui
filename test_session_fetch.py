import time
from src.app import app
from src.routes.terminal import _get_gemini_sessions_impl

with app.app_context():
    print("Fetching sessions...", flush=True)
    res = _get_gemini_sessions_impl(None, None, "local:local:", False, False)
    print(res)
