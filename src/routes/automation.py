from flask import Blueprint, jsonify, request
from src.services.schedule_manager import schedule_manager
from src.services.automation_bridge import automation_bridge

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


@automation_bp.route("/<schedule_id>", methods=["PUT"])
def update_schedule(schedule_id):
    # Missing update in manager, so delete and add
    schedule_manager.delete_schedule(schedule_id)
    return add_schedule()


@automation_bp.route("/<schedule_id>", methods=["DELETE"])
def delete_schedule(schedule_id):
    success = schedule_manager.delete_schedule(schedule_id)
    if success:
        return jsonify({"success": True}), 200
    return jsonify({"error": "Not found"}), 404


@automation_bp.route("/<schedule_id>/execute", methods=["POST"])
def execute_schedule(schedule_id):
    sched = schedule_manager.get_schedule(schedule_id)
    if not sched:
        return jsonify({"error": "Schedule not found"}), 404

    automation_bridge.execute_task(
        sched["target_host_id"], sched["task_prompt"], sched["prompt_context"]
    )
    return jsonify({"success": True}), 200
