from flask import Blueprint, render_template, request, redirect, jsonify, current_app
import uuid
import logging
from src.shared_state import ephemeral_sessions

logger = logging.getLogger(__name__)

ui_bp = Blueprint("ui", __name__)


@ui_bp.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@ui_bp.route("/test-launcher", methods=["GET"])
def test_launcher():
    return render_template("test_launcher.html")


@ui_bp.route("/fake_session_init", methods=["GET"])
def fake_session_init():
    scenario = request.args.get("scenario", "default")
    session_id = str(uuid.uuid4())
    ephemeral_sessions[session_id] = {
        "executable": "python3 src/mock_gemini_cli.py",
        "args": scenario,
        "used": False,
    }
    return redirect(f"/?session_id={session_id}&mode=fake")


@ui_bp.route("/favicon.ico", methods=["GET"])
@ui_bp.route("/favicon.svg", methods=["GET"])
def favicon():
    return current_app.send_static_file("favicon.svg")


@ui_bp.route("/manifest.json", methods=["GET"])
def manifest():
    return current_app.send_static_file("manifest.json")


@ui_bp.route("/sw.js", methods=["GET"])
def service_worker():
    response = current_app.send_static_file("sw.js")
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@ui_bp.route("/health", methods=["GET"])
def health_check_root():
    return jsonify({"status": "ok"})
