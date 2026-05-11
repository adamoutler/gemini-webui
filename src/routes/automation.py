from flask import Blueprint, jsonify, request
from src.services.schedule_manager import schedule_manager

automation_bp = Blueprint("automation", __name__, url_prefix="/api/v1/schedules")


@automation_bp.route("", methods=["GET"])
def list_schedules():
    schedules = schedule_manager.list_schedules()
    return jsonify(schedules)


@automation_bp.route("", methods=["POST"])
def add_schedule():
    data = request.json
    if not data or "target" not in data or "prompt" not in data:
        return jsonify({"error": "Missing required fields"}), 400

    target = data.get("target")
    prompt = data.get("prompt")
    recurrence = data.get("recurrence", "")
    mode = data.get("mode", "heuristic")
    wait_idle = mode == "heuristic"

    # We will simply store recurrence in cron_expr field for now
    cron_expr = recurrence if recurrence else "once"
    name = data.get("name", "Unnamed Task")

    schedule_id = schedule_manager.add_schedule(
        name=name,
        target_host_id=target,
        task_prompt=prompt,
        cron_expr=cron_expr,
        wait_for_idle=wait_idle,
    )

    return jsonify({"success": True, "id": schedule_id}), 201
