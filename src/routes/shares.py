import os
import re
from flask import Blueprint, jsonify, request, render_template

from src.app import authenticated_only, logger, share_manager

shares_bp = Blueprint("shares", __name__)


@shares_bp.route("/s/<share_id>", methods=["GET"])
def view_share(share_id):
    if not re.match(r"^[a-zA-Z0-9-]+$", share_id):
        return "Invalid share ID", 400

    metadata = share_manager.get_share_metadata(share_id)
    if not metadata:
        return "Share not found", 404

    file_path = metadata.get("file_path")
    if not file_path or not os.path.exists(file_path):
        return "Share data not found", 404

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    except Exception as e:
        logger.error(f"Failed to read share {share_id}: {e}")
        return "Error reading share data", 500

    return render_template(
        "share.html",
        session_name=metadata.get("session_name", "Unknown"),
        theme=metadata.get("theme", "dark"),
        html_content=html_content,
    )


@shares_bp.route("/api/shares/create", methods=["POST"])
@authenticated_only
def create_share():
    data = request.json
    if not data:
        return jsonify({"error": "No JSON payload"}), 400

    session_name = data.get("session_name")
    html_content = data.get("html_content")
    theme = data.get("theme", "dark")

    if not session_name or not html_content:
        return jsonify({"error": "Missing session_name or html_content"}), 400

    try:
        share_id = share_manager.create_share(html_content, session_name, theme)
        return jsonify({"share_id": share_id, "share_url": f"/s/{share_id}"})
    except Exception as e:
        logger.error(f"Error creating share: {e}")
        return jsonify({"error": "Failed to create share"}), 500


@shares_bp.route("/api/shares", methods=["GET"])
@authenticated_only
def list_shares():
    try:
        shares = share_manager.list_shares()
        return jsonify(shares)
    except Exception as e:
        logger.error(f"Error listing shares: {e}")
        return jsonify({"error": "Failed to list shares"}), 500


@shares_bp.route("/api/shares/<share_id>", methods=["DELETE"])
@authenticated_only
def delete_share(share_id):
    if not re.match(r"^[a-zA-Z0-9-]+$", share_id):
        return jsonify({"error": "Invalid share ID"}), 400

    try:
        success = share_manager.delete_share(share_id)
        if success:
            return jsonify({"status": "success"})
        else:
            return jsonify({"error": "Share not found"}), 404
    except Exception as e:
        logger.error(f"Error deleting share: {e}")
        return jsonify({"error": "Failed to delete share"}), 500
